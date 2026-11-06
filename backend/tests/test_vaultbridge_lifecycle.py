# VaultBridge Escrow simulation - backend regression tests
# NOTE: tests create NEW transactions (TEST_ names) and never touch seeded VB-ETH-2026-001 or call /admin/reset.
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
CREDS = {
    "admin": ("admin@vaultbridge.demo", "AdminDemo#2026"),
    "sender": ("sender@vaultbridge.demo", "SenderDemo#2026"),
    "recipient": ("recipient@vaultbridge.demo", "RecipientDemo#2026"),
}


def login(role):
    e, p = CREDS[role]
    r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
    assert r.status_code == 200, r.text
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="module")
def S():
    return {r: login(r) for r in CREDS}


def new_tx(S, name="TEST_Lifecycle"):
    r = S["admin"].post(f"{API}/transactions", json={"usd_value": 6_000_000_000, "sender_name": f"{name} Sender", "recipient_name": f"{name} Recipient"})
    assert r.status_code == 200, r.text
    tx = r.json()
    assert tx["reference"].startswith("VB-ETH-2026-")
    assert tx["current_step"] == 2 and tx["status"] == "Awaiting onboarding"
    assert abs(tx["eth_quantity"] - 2553191.489362) < 1e-6
    return tx


def act(s, tx_id, action, data=None):
    return s.post(f"{API}/transactions/{tx_id}/actions/{action}", json={"data": data or {}})


OB = {"legal_name": "TEST_Co", "registration_number": "R1", "jurisdiction": "Demo", "contact_name": "T",
      "contact_email": "t@example.com", "wallet_address": "0x" + "a" * 40, "fictional_confirmed": True}


# Auth
class TestAuth:
    def test_logins(self):
        for role, (e, p) in CREDS.items():
            r = requests.post(f"{API}/auth/login", json={"email": e, "password": p})
            assert r.status_code == 200 and r.json()["user"]["role"] == role

    def test_wrong_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": CREDS["admin"][0], "password": "nope"})
        assert r.status_code == 401

    def test_no_token(self):
        assert requests.get(f"{API}/transactions").status_code == 401

    def test_seed_tx_present(self, S):
        txs = S["admin"].get(f"{API}/transactions").json()
        assert any(t["reference"] == "VB-ETH-2026-001" for t in txs)


# Full 19-step lifecycle incl. ordering/role guards, decline/resend, onboarding reject, hold/resume, reports
class TestLifecycle:
    def test_full_flow(self, S):
        a, snd, rcp = S["admin"], S["sender"], S["recipient"]
        tx = new_tx(S)
        tid = tx["id"]
        # out-of-order / role violations
        assert act(snd, tid, "initiate_deposit", {"confirmed": True}).status_code == 400
        assert act(rcp, tid, "send_invitations").status_code in (400, 403)
        assert act(snd, tid, "accept_invitation").status_code == 400  # not sent yet
        assert act(a, tid, "send_invitations").status_code == 200
        assert act(a, tid, "send_invitations").status_code == 400
        # decline -> resend
        r = act(snd, tid, "decline_invitation"); assert r.json()["status"] == "Invitation declined"
        assert act(a, tid, "resend_invitation", {"party": "sender"}).status_code == 200
        assert act(snd, tid, "accept_invitation").json()["current_step"] == 4
        assert act(rcp, tid, "accept_invitation").json()["current_step"] == 5
        # onboarding validation, reject->resubmit
        bad = dict(OB, wallet_address="0x123")
        assert act(snd, tid, "submit_onboarding", bad).status_code == 400
        assert act(snd, tid, "submit_onboarding", OB).status_code == 200
        assert act(a, tid, "review_onboarding", {"party": "sender", "decision": "rejected", "note": "TEST"}).status_code == 200
        assert act(snd, tid, "submit_onboarding", OB).status_code == 200
        assert act(rcp, tid, "submit_onboarding", dict(OB, wallet_address="0x" + "b" * 40)).json()["current_step"] == 6
        assert act(a, tid, "issue_agreement").status_code == 400  # not approved yet
        for p in ("sender", "recipient"):
            assert act(a, tid, "review_onboarding", {"party": p, "decision": "approved"}).status_code == 200
        assert act(a, tid, "issue_agreement").json()["current_step"] == 7
        assert act(snd, tid, "accept_agreement", {}).status_code == 400
        assert act(snd, tid, "accept_agreement", {"confirmed": True}).status_code == 200
        assert act(rcp, tid, "accept_agreement", {"confirmed": True}).json()["current_step"] == 8
        # hold blocks actions
        assert act(a, tid, "hold").json()["status"] == "ON HOLD"
        assert a.post(f"{API}/invoices", json={"transaction_id": tid, "party": "recipient", "kind": "engagement", "items": ["escrow_admin"]}).status_code == 400
        assert act(a, tid, "resume").status_code == 200
        # engagement invoice
        assert a.post(f"{API}/invoices", json={"transaction_id": tid, "party": "sender", "kind": "engagement", "items": ["escrow_admin"]}).status_code == 400
        r = a.post(f"{API}/invoices", json={"transaction_id": tid, "party": "recipient", "kind": "engagement",
                                             "items": ["recipient_onboarding", "escrow_admin", "blockchain_analytics", "compliance", "custody_admin", "settlement_admin"]})
        assert r.status_code == 200; inv = r.json()
        assert inv["amount"] > 0
        assert act(snd, tid, "initiate_deposit", {"confirmed": True}).status_code == 400  # payment not confirmed
        assert a.post(f"{API}/invoices/{inv['id']}/confirm").status_code == 400  # not submitted
        assert snd.post(f"{API}/invoices/{inv['id']}/pay").status_code == 404  # not their invoice
        assert rcp.post(f"{API}/invoices/{inv['id']}/pay").status_code == 200
        assert rcp.post(f"{API}/invoices/{inv['id']}/confirm").status_code == 403
        assert a.post(f"{API}/invoices/{inv['id']}/confirm").json()["status"] == "Paid (Simulated)"
        # reports locked before availability
        assert rcp.get(f"{API}/reports/{tid}/deposit/pdf").status_code == 400
        r = rcp.get(f"{API}/reports/{tid}/engagement/pdf"); assert r.status_code == 200 and r.content[:4] == b"%PDF"
        # deposit
        assert act(rcp, tid, "initiate_deposit", {"confirmed": True}).status_code == 400
        t = act(snd, tid, "initiate_deposit", {"confirmed": True}).json()
        assert t["current_step"] == 12
        assert act(a, tid, "generate_analysis").status_code == 400
        time.sleep(26)
        t = a.get(f"{API}/transactions/{tid}").json()
        assert t["deposit"]["confirmations"] == 12 and t["current_step"] == 13
        assert act(a, tid, "complete_aml").status_code == 400
        assert act(a, tid, "generate_analysis").json()["current_step"] == 14
        assert act(a, tid, "complete_aml").status_code == 400  # checks not approved
        for k in t["compliance"]:
            assert act(a, tid, "set_compliance", {"check": k, "status": "Simulated Approval"}).status_code == 200
        assert act(a, tid, "complete_aml").json()["current_step"] == 15
        for s in (snd, rcp):
            r = s.get(f"{API}/reports/{tid}/compliance/pdf"); assert r.status_code == 200 and r.content[:4] == b"%PDF"
        t = a.get(f"{API}/transactions/{tid}").json(); assert t["current_step"] == 16
        assert act(rcp, tid, "request_settlement").status_code == 400
        assert act(snd, tid, "request_settlement").status_code == 200
        assert act(rcp, tid, "acknowledge_settlement").json()["current_step"] == 17
        assert act(a, tid, "decide_settlement", {"decision": "approved"}).json()["current_step"] == 18
        t = act(rcp, tid, "accept_balance").json()
        assert abs(t["recipient_wallet_balance"] - 2553191.489362) < 1e-6 and t["current_step"] == 19
        t = act(a, tid, "complete").json()
        assert t["status"] == "COMPLETED — SIMULATION"
        assert act(a, tid, "hold").status_code == 400
        # all 7 reports
        for rep in t["reports"]:
            assert rep["available"]
            r = snd.get(f"{API}/reports/{tid}/{rep['type']}/pdf")
            assert r.status_code == 200 and r.content[:4] == b"%PDF", rep["type"]
        r = rcp.get(f"{API}/invoices/{inv['id']}/pdf"); assert r.status_code == 200 and r.content[:4] == b"%PDF"
        # audit
        logs = snd.get(f"{API}/audit", params={"transaction_id": tid}).json()
        assert len(logs) > 10


# Fees, standard invoice, uploads, notifications, audit scope
class TestMisc:
    def test_fees_roundtrip(self, S):
        a = S["admin"]
        fees = a.get(f"{API}/fees").json()
        assert len(fees) == 7
        r = a.put(f"{API}/fees", json=fees)  # unchanged values; persistence round-trip
        assert r.status_code == 200
        assert S["recipient"].put(f"{API}/fees", json=fees).status_code == 403
        bad = [dict(fees[0], amount=-1)] + fees[1:]
        assert a.put(f"{API}/fees", json=bad).status_code == 400

    def test_standard_invoice_and_upload(self, S):
        a, snd, rcp = S["admin"], S["sender"], S["recipient"]
        tx = new_tx(S, "TEST_Misc")
        tid = tx["id"]
        inv = a.post(f"{API}/invoices", json={"transaction_id": tid, "party": "sender", "kind": "standard", "items": ["sender_onboarding"]}).json()
        assert inv["status"] == "Issued"
        assert inv["id"] not in [i["id"] for i in rcp.get(f"{API}/invoices").json()]
        assert snd.post(f"{API}/invoices/{inv['id']}/pay").status_code == 200
        assert a.post(f"{API}/invoices/{inv['id']}/confirm").json()["status"] == "Paid (Simulated)"
        files = {"file": ("TEST_doc.pdf", b"%PDF-1.4 test", "application/pdf")}
        r = a.post(f"{API}/reports/{tid}/uploads", data={"title": "TEST_upload"}, files=files)
        assert r.status_code == 200, r.text
        up = r.json()
        assert snd.post(f"{API}/reports/{tid}/uploads", data={"title": "x"}, files=files).status_code == 403
        lst = rcp.get(f"{API}/reports/{tid}/uploads").json()
        assert any(u["id"] == up["id"] for u in lst)
        d = rcp.get(f"{API}/reports/uploads/{up['id']}/download"); assert d.status_code == 200 and d.content == b"%PDF-1.4 test"

    def test_notifications(self, S):
        s = S["sender"]
        n = s.get(f"{API}/notifications").json()
        assert len(n) > 0 and any(x["kind"] == "email" for x in n)
        assert s.post(f"{API}/notifications/{n[0]['id']}/read").status_code == 200
        assert s.post(f"{API}/notifications/read-all").status_code == 200
        assert all(x["read"] for x in s.get(f"{API}/notifications").json())

    def test_users_admin_only(self, S):
        assert S["sender"].get(f"{API}/users").status_code == 403
        assert S["sender"].post(f"{API}/admin/reset").status_code == 403
        assert S["admin"].get(f"{API}/users").status_code == 200
