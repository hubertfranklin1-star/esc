# Regression: onboarding fee pay-to wallet (admin setting), on-chain tx-hash verification via Etherscan, manual "I've paid" path
# Run sequentially: pytest -n 0 -p no:randomly. State persisted in /tmp/feewallet_state.json so phases can be run separately with -k.
import json
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
STATE = "/tmp/feewallet_state.json"
FEE_WALLET = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
REAL_HASH = "0xd75f67f4cf551015772d8c6e7c53328ef4f12153819367ab9f2865c7d99f53f1"  # 0.0133774915708334 ETH -> FEE_WALLET
REAL_FROM = "0x65604502cae188bd6cce556dd4e8a20213667328"
PW = "TestPass#2026"
JOIN_WALLET = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


def load():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def save(s):
    json.dump(s, open(STATE, "w"))


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    if r.status_code != 200:
        pytest.skip(f"login failed {email}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin():
    return hdr(login("admin@vaultbridge.demo", "AdminDemo#2026"))


def act(h, tid, action, data=None):
    return requests.post(f"{API}/transactions/{tid}/actions/{action}", headers=h, json={"data": data or {}})


def join(h, tid):
    r = act(h, tid, "join", {"legal_name": "TEST Co", "contact_name": "TEST", "contact_email": "a@resend.dev",
                             "wallet_address": JOIN_WALLET, "rules_accepted": True})
    assert r.status_code == 200, r.text
    return r.json()


def inv_of(h, tid, party):
    tx = requests.get(f"{API}/transactions/{tid}", headers=h).json()
    iid = tx["onboarding_fees"][party]["invoice_id"]
    return next(i for i in requests.get(f"{API}/invoices?transaction_id={tid}", headers=h).json() if i["id"] == iid), tx


# setup: fee 0.01 without wallet, two deals, A sender @0.01, A recipient @0.5, B both @0.01
def test_01_setup(admin):
    run = uuid.uuid4().hex[:6]
    r = requests.put(f"{API}/onboarding-fee", headers=admin, json={"amount_eth": 0.01})
    assert r.status_code == 200
    g = requests.get(f"{API}/onboarding-fee", headers=admin).json()
    assert g["amount_eth"] == 0.01 and g["wallet"] == ""
    s = {"run": run}
    for d in ("A", "B"):
        se, re_ = f"test_fw{d.lower()}_s_{run}@resend.dev", f"test_fw{d.lower()}_r_{run}@resend.dev"
        r = requests.post(f"{API}/transactions", headers=admin, json={
            "usd_value": 250000, "sender_name": f"TEST_FW{d} Sender", "recipient_name": f"TEST_FW{d} Recipient",
            "sender_email": se, "recipient_email": re_})
        assert r.status_code == 200, r.text
        s[d] = {"id": r.json()["id"], "ref": r.json()["reference"], "s_email": se, "r_email": re_}
        for k, e in (("s", se), ("r", re_)):
            rr = requests.post(f"{API}/auth/register", json={"email": e, "password": PW, "name": f"TEST {k}"})
            assert rr.status_code == 200, rr.text
            s[d][k] = rr.json()["token"]
    join(hdr(s["A"]["s"]), s["A"]["id"])
    join(hdr(s["B"]["s"]), s["B"]["id"])
    join(hdr(s["B"]["r"]), s["B"]["id"])
    assert requests.put(f"{API}/onboarding-fee", headers=admin, json={"amount_eth": 0.5}).status_code == 200
    join(hdr(s["A"]["r"]), s["A"]["id"])
    assert requests.put(f"{API}/onboarding-fee", headers=admin, json={"amount_eth": 0.01}).status_code == 200
    ia, _ = inv_of(admin, s["A"]["id"], "sender")
    ib, _ = inv_of(admin, s["A"]["id"], "recipient")
    assert ia["amount"] == 0.01 and ia["currency"] == "ETH" and ia["kind"] == "onboarding"
    assert ib["amount"] == 0.5
    save(s)


# no wallet configured -> pay is blocked
def test_02_missing_wallet(admin):
    s = load()
    inv, _ = inv_of(admin, s["A"]["id"], "sender")
    for body in (None, {"tx_hash": REAL_HASH}):
        r = requests.post(f"{API}/invoices/{inv['id']}/pay", headers=hdr(s["A"]["s"]), json=body)
        assert r.status_code == 400
        assert "hasn't set the payment wallet" in r.json()["detail"]
    inv2, _ = inv_of(admin, s["A"]["id"], "sender")
    assert inv2["status"] == "Unpaid"


# admin sets wallet; validation; RBAC
def test_03_wallet_settings(admin):
    s = load()
    r = requests.put(f"{API}/onboarding-fee", headers=hdr(s["A"]["s"]), json={"amount_eth": 0.01, "wallet": FEE_WALLET})
    assert r.status_code == 403
    for bad in ("0x123", "abc", "0x" + "g" * 40, "  "):
        r = requests.put(f"{API}/onboarding-fee", headers=admin, json={"amount_eth": 0.01, "wallet": bad})
        assert r.status_code == 400, (bad, r.text)
    assert requests.get(f"{API}/onboarding-fee", headers=admin).json()["wallet"] == ""
    r = requests.put(f"{API}/onboarding-fee", headers=admin, json={"amount_eth": 0.01, "wallet": "  " + FEE_WALLET + " "})
    assert r.status_code == 200
    assert r.json() == {"amount_eth": 0.01, "wallet": FEE_WALLET}
    g = requests.get(f"{API}/onboarding-fee", headers=hdr(s["A"]["s"]))
    assert g.status_code == 200 and g.json() == {"amount_eth": 0.01, "wallet": FEE_WALLET}
    # amount-only update keeps wallet
    requests.put(f"{API}/onboarding-fee", headers=admin, json={"amount_eth": 0.01})
    assert requests.get(f"{API}/onboarding-fee", headers=admin).json()["wallet"] == FEE_WALLET


# verification negatives
def test_04_verify_negatives(admin):
    s = load()
    inv, _ = inv_of(admin, s["A"]["id"], "sender")
    url = f"{API}/invoices/{inv['id']}/pay"
    r = requests.post(url, headers=hdr(s["A"]["s"]), json={"tx_hash": "0x1234"})
    assert r.status_code == 400 and "64 hex" in r.json()["detail"]
    r = requests.post(url, headers=hdr(s["A"]["s"]), json={"tx_hash": "0x" + "ab" * 32})
    assert r.status_code == 400 and "not found" in r.json()["detail"].lower(), r.text
    # recipient invoice is 0.5 ETH > tx value
    rinv, _ = inv_of(admin, s["A"]["id"], "recipient")
    r = requests.post(f"{API}/invoices/{rinv['id']}/pay", headers=hdr(s["A"]["r"]), json={"tx_hash": REAL_HASH})
    assert r.status_code == 400, r.text
    assert "0.0134 ETH" in r.json()["detail"] and "0.5 ETH" in r.json()["detail"]
    # wrong party can't pay
    r = requests.post(url, headers=hdr(s["A"]["r"]), json={"tx_hash": REAL_HASH})
    assert r.status_code in (400, 403, 404)
    inv2, _ = inv_of(admin, s["A"]["id"], "sender")
    assert inv2["status"] == "Unpaid"


# real mainnet tx verifies
def test_05_verify_success(admin):
    s = load()
    inv, _ = inv_of(admin, s["A"]["id"], "sender")
    r = requests.post(f"{API}/invoices/{inv['id']}/pay", headers=hdr(s["A"]["s"]), json={"tx_hash": REAL_HASH})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "Paid" and d["verified_onchain"] is True
    assert d["payment_from"].lower() == REAL_FROM
    assert d["payment_tx_hash"] == REAL_HASH.lower() and d["payment_to"] == FEE_WALLET
    assert isinstance(d["payment_block"], int) and d["paid_at"]
    inv2, tx = inv_of(admin, s["A"]["id"], "sender")
    assert inv2["status"] == "Paid"
    of = tx["onboarding_fees"]["sender"]
    assert of["submitted_at"] and of["confirmed_at"] and of["tx_hash"] == REAL_HASH
    assert tx["current_step"] == 3


# reuse of same hash rejected (also case-variant)
def test_06_reuse(admin):
    s = load()
    rinv, _ = inv_of(admin, s["A"]["id"], "recipient")
    for h in (REAL_HASH, "0x" + REAL_HASH[2:].upper()):
        r = requests.post(f"{API}/invoices/{rinv['id']}/pay", headers=hdr(s["A"]["r"]), json={"tx_hash": h})
        assert r.status_code == 400 and "already been used" in r.json()["detail"], r.text


# manual path -> Payment Sent -> step 4 -> approve marks Paid
def test_07_manual_and_approve(admin):
    s = load()
    rinv, _ = inv_of(admin, s["A"]["id"], "recipient")
    r = requests.post(f"{API}/invoices/{rinv['id']}/pay", headers=hdr(s["A"]["r"]))
    assert r.status_code == 200 and r.json()["status"] == "Payment Sent"
    assert r.json().get("payment_to") == FEE_WALLET and not r.json().get("verified_onchain")
    _, tx = inv_of(admin, s["A"]["id"], "recipient")
    assert tx["current_step"] == 4
    assert tx["onboarding_fees"]["recipient"]["submitted_at"] and not tx["onboarding_fees"]["recipient"]["confirmed_at"]
    # double pay blocked
    assert requests.post(f"{API}/invoices/{rinv['id']}/pay", headers=hdr(s["A"]["r"])).status_code == 400
    r = act(admin, s["A"]["id"], "approve_parties")
    assert r.status_code == 200 and r.json()["current_step"] == 5
    rinv2, tx = inv_of(admin, s["A"]["id"], "recipient")
    assert rinv2["status"] == "Paid" and tx["onboarding_fees"]["recipient"]["confirmed_at"]


# escrow fee invoice (engagement) still pays with no body
def test_08_engagement_no_body(admin):
    s = load()
    tid = s["A"]["id"]
    assert act(hdr(s["A"]["s"]), tid, "deposit").status_code == 200
    time.sleep(26)
    requests.get(f"{API}/transactions/{tid}", headers=admin)
    r = act(admin, tid, "verify_deposit")
    assert r.status_code == 200, r.text
    up = requests.post(f"{API}/reports/{tid}/uploads", headers=admin, data={"title": "TEST_fw doc", "category": "forensic"},
                       files={"file": ("TEST_fw.txt", b"x", "text/plain")})
    assert up.status_code == 200
    assert act(admin, tid, "release_aml_report").status_code == 200
    r = act(hdr(s["A"]["r"]), tid, "request_release")
    assert r.status_code == 200, r.text
    inv_id = r.json()["payment"]["invoice_id"]
    r = requests.post(f"{API}/invoices/{inv_id}/pay", headers=hdr(s["A"]["r"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Payment Sent" and r.json()["kind"] == "engagement"
    assert requests.get(f"{API}/transactions/{tid}", headers=admin).json()["current_step"] == 10
