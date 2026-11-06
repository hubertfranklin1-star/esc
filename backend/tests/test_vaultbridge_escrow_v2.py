# VaultBridge Escrow (simplified 10-step flow) regression tests
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


def new_deal(S, value=4700000.0):
    r = S["admin"].post(f"{API}/transactions", json={"usd_value": value, "sender_name": "TEST_Sender Co", "recipient_name": "TEST_Recipient Co"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["current_step"] == 1 and d["status"] == "Awaiting onboarding"
    return d


def act(S, role, tx_id, action, data=None):
    return S[role].post(f"{API}/transactions/{tx_id}/actions/{action}", json={"data": data or {}})


def join_data(role):
    return {"legal_name": f"TEST_{role}", "contact_name": "TEST Person", "contact_email": f"{role}@x.io", "wallet_address": "0x" + "a" * 40}


def to_step(S, tx_id, target):
    """Drive the deal up to (not including) `target` step."""
    steps = [
        lambda: act(S, "sender", tx_id, "join", join_data("sender")),
        lambda: act(S, "recipient", tx_id, "join", join_data("recipient")),
        lambda: act(S, "admin", tx_id, "approve_parties"),
        lambda: (act(S, "sender", tx_id, "sign_agreement"), act(S, "recipient", tx_id, "sign_agreement"))[1],
    ]
    for i, fn in enumerate(steps[: target - 1]):
        r = fn()
        assert r.status_code == 200, (i, r.text)
    tx = S["admin"].get(f"{API}/transactions/{tx_id}").json()
    if target > 5:
        inv = tx["payment"]["invoice_id"]
        assert S["recipient"].post(f"{API}/invoices/{inv}/pay").status_code == 200
    if target > 6:
        assert S["admin"].post(f"{API}/invoices/{inv}/confirm").status_code == 200
    if target > 7:
        assert act(S, "sender", tx_id, "deposit").status_code == 200
    return S["admin"].get(f"{API}/transactions/{tx_id}").json()


# Auth basics
class TestAuth:
    def test_login_and_me(self, S):
        for role in CREDS:
            r = S[role].get(f"{API}/auth/me")
            assert r.status_code == 200 and r.json()["role"] == role

    def test_bad_login_and_no_token(self):
        assert requests.post(f"{API}/auth/login", json={"email": "admin@vaultbridge.demo", "password": "x"}).status_code == 401
        assert requests.get(f"{API}/transactions").status_code == 401


# Full 10-step happy path
class TestFullFlow:
    def test_full_flow(self, S):
        tx = new_deal(S, 6_000_000_000.0)
        tid = tx["id"]
        assert len(tx["steps"]) == 10
        t = to_step(S, tid, 5)
        assert t["current_step"] == 5 and t["payment"]["invoice_id"]
        inv_id = t["payment"]["invoice_id"]
        inv = S["recipient"].get(f"{API}/invoices?transaction_id={tid}").json()
        assert any(i["id"] == inv_id and i["kind"] == "engagement" and i["amount"] == 2650000 for i in inv)
        # sender cannot pay recipient invoice
        assert S["sender"].post(f"{API}/invoices/{inv_id}/pay").status_code in (403, 404)
        assert S["recipient"].post(f"{API}/invoices/{inv_id}/pay").json()["status"] == "Payment Sent"
        assert S["recipient"].post(f"{API}/invoices/{inv_id}/confirm").status_code == 403
        assert S["admin"].post(f"{API}/invoices/{inv_id}/confirm").json()["status"] == "Paid"
        assert S["admin"].get(f"{API}/transactions/{tid}").json()["current_step"] == 7
        assert act(S, "recipient", tid, "deposit").status_code == 403
        r = act(S, "sender", tid, "deposit")
        assert r.status_code == 200 and r.json()["current_step"] == 8
        early = act(S, "admin", tid, "verify_deposit")
        assert early.status_code == 400 and "12" in early.json()["detail"]
        assert S["admin"].get(f"{API}/reports/{tid}/deposit/pdf").status_code == 400
        time.sleep(26)
        t = S["admin"].get(f"{API}/transactions/{tid}").json()
        assert t["deposit"]["confirmations"] == 12
        r = act(S, "admin", tid, "verify_deposit")
        assert r.status_code == 200 and r.json()["current_step"] == 9
        assert act(S, "recipient", tid, "request_release").status_code == 403
        assert act(S, "sender", tid, "request_release").json()["current_step"] == 10
        # decline -> back to step 9
        r = act(S, "admin", tid, "release", {"decision": "rejected", "note": "TEST"})
        assert r.json()["current_step"] == 9
        act(S, "sender", tid, "request_release")
        r = act(S, "admin", tid, "release", {"decision": "approved"})
        d = r.json()
        assert d["status"] == "Completed" and round(d["recipient_wallet_balance"], 2) == 2553191.49
        for kind in ("agreement", "deposit", "verification", "final"):
            p = S["sender"].get(f"{API}/reports/{tid}/{kind}/pdf")
            assert p.status_code == 200 and p.content[:4] == b"%PDF", kind
        assert act(S, "admin", tid, "hold").status_code == 400  # completed


# Guards, order and role checks
class TestGuards:
    def test_out_of_order(self, S):
        tid = new_deal(S)["id"]
        assert act(S, "admin", tid, "approve_parties").status_code == 400
        assert act(S, "sender", tid, "sign_agreement").status_code == 400
        assert act(S, "sender", tid, "deposit").status_code == 400
        assert act(S, "admin", tid, "join", join_data("x")).status_code == 403
        assert act(S, "sender", tid, "approve_parties").status_code == 403
        assert act(S, "sender", tid, "join", {**join_data("sender"), "wallet_address": "0x12"}).status_code == 400
        assert act(S, "sender", tid, "join", {"legal_name": "a"}).status_code == 400
        assert act(S, "sender", tid, "bogus").status_code == 400
        assert S["sender"].get(f"{API}/reports/{tid}/agreement/pdf").status_code == 400

    def test_decline_and_resend(self, S):
        tid = new_deal(S)["id"]
        r = act(S, "sender", tid, "decline")
        assert r.json()["status"] == "Invitation declined"
        assert act(S, "sender", tid, "join", join_data("sender")).status_code == 400
        assert act(S, "sender", tid, "resend_invitation", {"party": "sender"}).status_code == 403
        r = act(S, "admin", tid, "resend_invitation", {"party": "sender"})
        assert r.status_code == 200 and r.json()["invitations"]["sender"]["status"] == "pending"
        assert act(S, "sender", tid, "join", join_data("sender")).status_code == 200

    def test_reject_party_and_rejoin(self, S):
        tid = new_deal(S)["id"]
        to_step(S, tid, 3)
        r = act(S, "admin", tid, "reject_party", {"party": "sender", "note": "TEST fix name"})
        d = r.json()
        assert d["current_step"] == 1 and d["onboarding"]["sender"]["note"] == "TEST fix name"
        assert act(S, "sender", tid, "join", join_data("sender")).json()["current_step"] == 3

    def test_hold_blocks(self, S):
        tid = new_deal(S)["id"]
        assert act(S, "admin", tid, "hold").json()["status"] == "On hold"
        assert act(S, "sender", tid, "join", join_data("sender")).status_code == 400
        assert act(S, "admin", tid, "resume").json()["on_hold"] is False
        assert act(S, "sender", tid, "join", join_data("sender")).status_code == 200

    def test_compliance_rejected_blocks_verify(self, S):
        tid = new_deal(S)["id"]
        to_step(S, tid, 8)
        assert act(S, "sender", tid, "set_compliance", {"check": "sanctions", "status": "Rejected"}).status_code == 403
        assert act(S, "admin", tid, "set_compliance", {"check": "sanctions", "status": "Rejected"}).status_code == 200
        time.sleep(26)
        r = act(S, "admin", tid, "verify_deposit")
        assert r.status_code == 400 and "Rejected" in r.json()["detail"]
        act(S, "admin", tid, "set_compliance", {"check": "sanctions", "status": "Approved"})
        assert act(S, "admin", tid, "verify_deposit").status_code == 200


# Fees, invoices, uploads, notifications, audit
class TestMisc:
    def test_fees_roundtrip(self, S):
        fees = S["admin"].get(f"{API}/fees").json()
        assert len(fees) == 7
        assert S["sender"].put(f"{API}/fees", json=fees).status_code == 403
        bad = [dict(f, amount=-1) if i == 0 else f for i, f in enumerate(fees)]
        assert S["admin"].put(f"{API}/fees", json=bad).status_code == 400
        mod = [dict(f, amount=f["amount"] + 1) if f["code"] == "sender_onboarding" else f for f in fees]
        assert S["admin"].put(f"{API}/fees", json=mod).status_code == 200
        assert next(f for f in S["sender"].get(f"{API}/fees").json() if f["code"] == "sender_onboarding")["amount"] == fees[0]["amount"] + 1
        S["admin"].put(f"{API}/fees", json=fees)

    def test_new_invoice_and_pdf(self, S):
        tid = new_deal(S)["id"]
        r = S["admin"].post(f"{API}/invoices", json={"transaction_id": tid, "party": "sender", "items": ["sender_onboarding"]})
        assert r.status_code == 200
        inv = r.json()
        assert inv["party"] == "sender" and inv["status"] == "Unpaid"
        assert S["sender"].post(f"{API}/invoices", json={"transaction_id": tid, "party": "sender", "items": ["sender_onboarding"]}).status_code == 403
        assert any(i["id"] == inv["id"] for i in S["sender"].get(f"{API}/invoices?transaction_id={tid}").json())
        assert not any(i["id"] == inv["id"] for i in S["recipient"].get(f"{API}/invoices?transaction_id={tid}").json())
        p = S["sender"].get(f"{API}/invoices/{inv['id']}/pdf")
        assert p.status_code == 200 and p.content[:4] == b"%PDF"
        assert S["recipient"].get(f"{API}/invoices/{inv['id']}/pdf").status_code == 404

    def test_upload_download(self, S):
        tid = new_deal(S)["id"]
        r = S["admin"].post(f"{API}/reports/{tid}/uploads", data={"title": "TEST_doc"}, files={"file": ("t.txt", b"hello", "text/plain")})
        assert r.status_code == 200
        uid = r.json()["id"]
        assert S["sender"].post(f"{API}/reports/{tid}/uploads", data={"title": "x"}, files={"file": ("t.txt", b"a", "text/plain")}).status_code == 403
        d = S["recipient"].get(f"{API}/reports/uploads/{uid}/download")
        assert d.status_code == 200 and d.content == b"hello"

    def test_invitation_notifications_and_audit(self, S):
        d = new_deal(S)
        notes = S["sender"].get(f"{API}/notifications").json()
        assert any(n["transaction_id"] == d["id"] and n["kind"] == "email" for n in notes)
        notes = S["recipient"].get(f"{API}/notifications").json()
        assert any(n["transaction_id"] == d["id"] for n in notes)
        audit = S["admin"].get(f"{API}/audit?transaction_id={d['id']}").json()
        assert any(a["action"] == "Transaction created" for a in audit)
        assert S["sender"].get(f"{API}/users").status_code == 403
