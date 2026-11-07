# Regression: launch cleanup + 50/50 escrow fee split (steps 4-10), deposit to admin wallet, share-invoice on-chain verify, decline/release.
# Run sequentially: pytest -n 0 -p no:randomly /app/backend/tests/test_fee_split_launch.py
# Needs direct DB access only to unset the pay-to wallet (no API to clear it). Restores fees + onboarding fee at the end.
import asyncio
import io
import os
import time
import uuid

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
WALLET = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
PARTY_WALLET = "0x65604502cae188bd6cce556dd4e8a20213667328"
USED_HASH = "0xd75f67f4cf551015772d8c6e7c53328ef4f12153819367ab9f2865c7d99f53f1"
OLD_HASH = "0x337ee39459dd802c05f566ff8c1898bb99703eb307594cbd2e5d2945af85ff7a"  # 0.00369 ETH -> WALLET, unused, mined long ago
UNKNOWN_HASH = "0x" + "ab" * 32
PW = "TestPass#2026"
ORIG_FEES = [
    {"code": "escrow_admin", "label": "Escrow administration", "amount": 1500000, "party": "recipient"},
    {"code": "blockchain_analytics", "label": "Blockchain analytics", "amount": 75000, "party": "recipient"},
    {"code": "compliance", "label": "Compliance assessment", "amount": 150000, "party": "recipient"},
    {"code": "custody_admin", "label": "Custody administration", "amount": 600000, "party": "recipient"},
    {"code": "settlement_admin", "label": "Settlement administration", "amount": 300000, "party": "recipient"},
]
S = {}


def hdr(t):
    return {"Authorization": f"Bearer {t}"}


def act(h, action, data=None):
    return requests.post(f"{API}/transactions/{S['tid']}/actions/{action}", headers=h, json={"data": data or {}}, timeout=60)


def tx(h=None):
    return requests.get(f"{API}/transactions/{S['tid']}", headers=h or S["admin"]).json()


def invoices(h=None):
    return requests.get(f"{API}/invoices?transaction_id={S['tid']}", headers=h or S["admin"]).json()


def unset_wallet():
    load_dotenv("/app/backend/.env")
    async def m():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        await c[os.environ["DB_NAME"]].settings.update_one({"key": "onboarding_fee"}, {"$unset": {"wallet": ""}})
        c.close()
    asyncio.run(m())


@pytest.fixture(scope="module", autouse=True)
def setup_and_restore():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@vaultbridge.demo", "password": "AdminDemo#2026"})
    assert r.status_code == 200
    S["admin"] = hdr(r.json()["token"])
    yield
    requests.put(f"{API}/fees", headers=S["admin"], json=ORIG_FEES)
    requests.put(f"{API}/onboarding-fee", headers=S["admin"], json={"amount_eth": 6.5})


def test_01_create_deal_live_price_and_register():
    u = uuid.uuid4().hex[:8]
    S["se"], S["re"] = f"test_s_{u}@resend.dev", f"test_r_{u}@resend.dev"
    r = requests.post(f"{API}/transactions", headers=S["admin"], json={"usd_value": 10000, "sender_name": "TEST_Sender Co",
                      "recipient_name": "TEST_Recipient Co", "sender_email": S["se"], "recipient_email": S["re"]}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    S["tid"] = d["id"]
    S["ref"] = d["reference"]
    assert 500 < d["eth_price"] < 20000 and d["eth_price"] != 2350.0
    assert abs(d["eth_quantity"] - round(10000 / d["eth_price"], 6)) < 1e-6
    for k, e in (("s", S["se"]), ("r", S["re"])):
        rr = requests.post(f"{API}/auth/register", json={"email": e, "password": PW, "name": f"TEST {k}"})
        assert rr.status_code == 200, rr.text
        S[k] = hdr(rr.json()["token"])


def test_02_join_rejects_invalid_wallet_then_joins():
    bad = act(S["s"], "join", {"legal_name": "TEST Co", "contact_name": "T", "contact_email": S["se"], "wallet_address": "0x123", "rules_accepted": True})
    assert bad.status_code == 400 and "40 hex" in bad.json()["detail"]
    empty = act(S["s"], "join", {"legal_name": "TEST Co", "contact_name": "T", "contact_email": S["se"], "wallet_address": "", "rules_accepted": True})
    assert empty.status_code == 400
    for k, e in (("s", S["se"]), ("r", S["re"])):
        r = act(S[k], "join", {"legal_name": "TEST Co", "contact_name": "T", "contact_email": e, "wallet_address": PARTY_WALLET, "rules_accepted": True})
        assert r.status_code == 200, r.text
    assert tx()["current_step"] == 3


def test_03_pay_onboarding_then_approve_requires_wallet():
    assert requests.put(f"{API}/onboarding-fee", headers=S["admin"], json={"amount_eth": 6.5, "wallet": WALLET}).status_code == 200
    t = tx()
    for k, p in (("s", "sender"), ("r", "recipient")):
        r = requests.post(f"{API}/invoices/{t['onboarding_fees'][p]['invoice_id']}/pay", headers=S[k], json={})
        assert r.status_code == 200 and r.json()["status"] == "Payment Sent"
    assert tx()["current_step"] == 4
    unset_wallet()
    r = act(S["admin"], "approve_parties")
    assert r.status_code == 400 and "wallet" in r.json()["detail"].lower()
    assert requests.put(f"{API}/onboarding-fee", headers=S["admin"], json={"amount_eth": 6.5, "wallet": WALLET}).status_code == 200
    r = act(S["admin"], "approve_parties")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["escrow_vault_address"] == WALLET and d["current_step"] == 5


def test_04_deposit_errors():
    r = act(S["s"], "deposit", {"tx_hash": "0x123"})
    assert r.status_code == 400 and "64 hex" in r.json()["detail"]
    r = act(S["s"], "deposit", {"tx_hash": UNKNOWN_HASH})
    assert r.status_code == 400 and "not found" in r.json()["detail"].lower(), r.text
    r = act(S["s"], "deposit", {"tx_hash": USED_HASH})
    assert r.status_code == 400 and "sent 0.0134 ETH" in r.json()["detail"], r.text
    r = act(S["s"], "deposit", {"tx_hash": OLD_HASH})
    assert r.status_code == 400, r.text
    S["deposit_small_msg"] = r.json()["detail"]
    print("small deposit msg:", S["deposit_small_msg"])
    assert act(S["r"], "deposit").status_code == 403
    assert tx()["current_step"] == 5


def test_05_manual_deposit_and_admin_confirm():
    r = act(S["s"], "deposit")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "Deposit awaiting confirmation" and d["current_step"] == 6
    assert d["deposit"]["to_address"] == WALLET and d["deposit"]["confirmed_at"] is None and d["deposit"]["tx_hash"] is None
    r = act(S["admin"], "verify_deposit")
    assert r.status_code == 200
    d = r.json()
    assert d["deposit"]["confirmed_at"] and d["current_step"] == 7
    files = {"file": ("aml.txt", io.BytesIO(b"TEST aml"), "text/plain")}
    up = requests.post(f"{API}/reports/{S['tid']}/uploads", headers=S["admin"], data={"title": "TEST AML", "category": "forensic"}, files=files)
    assert up.status_code == 200
    assert act(S["admin"], "release_aml_report").status_code == 200
    assert tx()["current_step"] == 8


def test_06_request_release_creates_two_half_invoices():
    assert act(S["s"], "request_release").status_code == 403
    assert act(S["admin"], "release", {"decision": "approved"}).status_code == 400
    r = act(S["r"], "request_release")
    assert r.status_code == 200, r.text
    d = r.json()
    price = d["settlement_fee_price"]["eth_usd"]
    assert 500 < price < 20000
    assert d["current_step"] == 9 and d["status"] == "Escrow fees due"
    invs = {i["id"]: i for i in invoices()}
    for p in ("sender", "recipient"):
        sf = d["settlement_fees"][p]
        assert sf["usd_amount"] == 1312500
        assert abs(sf["eth_amount"] - 1312500 / price) < 0.0001
        inv = invs[sf["invoice_id"]]
        assert inv["kind"] == "engagement" and inv["currency"] == "ETH" and inv["party"] == p and inv["status"] == "Unpaid"
    S["inv1"] = {p: d["settlement_fees"][p]["invoice_id"] for p in ("sender", "recipient")}
    # parties see only their own invoice
    assert [i["party"] for i in invoices(S["s"])].count("recipient") == 0


def test_07_one_party_pays_others_see_it():
    assert requests.post(f"{API}/invoices/{S['inv1']['recipient']}/pay", headers=S["s"], json={}).status_code in (403, 404)
    r = requests.post(f"{API}/invoices/{S['inv1']['sender']}/pay", headers=S["s"], json={})
    assert r.status_code == 200 and r.json()["status"] == "Payment Sent"
    d = tx(S["r"])
    assert d["settlement_fees"]["sender"]["submitted_at"] and not d["settlement_fees"]["recipient"]["submitted_at"]
    assert d["current_step"] == 9
    assert act(S["admin"], "release", {"decision": "approved"}).status_code == 400
    r = requests.post(f"{API}/invoices/{S['inv1']['recipient']}/pay", headers=S["r"], json={})
    assert r.status_code == 200
    assert tx()["current_step"] == 10 and tx()["status"] == "Release pending"


def test_08_decline_goes_back_to_step8_and_cancels():
    r = act(S["admin"], "release", {"decision": "rejected", "note": "TEST decline"})
    assert r.status_code == 200
    d = r.json()
    assert d["current_step"] == 8 and d["settlement_fees"] == {}
    invs = {i["id"]: i for i in invoices()}
    for p in ("sender", "recipient"):
        assert invs[S["inv1"][p]]["status"] == "Cancelled"


def test_09_tiny_fees_share_verify_errors():
    tiny = [{**f, "amount": 1} for f in ORIG_FEES]
    assert requests.put(f"{API}/fees", headers=S["admin"], json=tiny).status_code == 200
    r = act(S["r"], "request_release")
    requests.put(f"{API}/fees", headers=S["admin"], json=ORIG_FEES)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["settlement_fees"]["sender"]["usd_amount"] == 2.5
    S["inv2"] = {p: d["settlement_fees"][p]["invoice_id"] for p in ("sender", "recipient")}
    sid = S["inv2"]["sender"]
    pay = lambda h: requests.post(f"{API}/invoices/{sid}/pay", headers=S["s"], json={"tx_hash": h}, timeout=60)
    r = pay("0xzz")
    assert r.status_code == 400 and "64 hex" in r.json()["detail"]
    r = pay(UNKNOWN_HASH)
    assert r.status_code == 400 and "not found" in r.json()["detail"].lower()
    time.sleep(1.5)
    r = pay(USED_HASH.upper().replace("0X", "0x"))  # upper-case hash accepted, old tx rejected by mined time
    assert r.status_code == 400 and "sent before this payment was requested" in r.json()["detail"], r.text
    time.sleep(1.5)
    r = pay(OLD_HASH)
    assert r.status_code == 400 and "sent before this payment was requested" in r.json()["detail"], r.text
    assert tx()["settlement_fees"]["sender"]["submitted_at"] is None


def test_10_manual_pay_admin_confirm_release_complete():
    for k, p in (("s", "sender"), ("r", "recipient")):
        assert requests.post(f"{API}/invoices/{S['inv2'][p]}/pay", headers=S[k], json={}).status_code == 200
    r = requests.post(f"{API}/invoices/{S['inv2']['sender']}/confirm", headers=S["admin"])
    assert r.status_code == 200 and r.json()["status"] == "Paid"
    assert requests.post(f"{API}/invoices/{S['inv2']['sender']}/confirm", headers=S["s"]).status_code == 403
    d = tx()
    assert d["settlement_fees"]["sender"]["confirmed_at"] and not d["settlement_fees"]["recipient"]["confirmed_at"]
    assert d["current_step"] == 10
    r = act(S["admin"], "release", {"decision": "approved", "tx_hash": "0x12"})
    assert r.status_code == 400
    r = act(S["admin"], "release", {"decision": "approved"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "Completed" and d["completed_at"]
    invs = {i["id"]: i for i in invoices()}
    assert all(invs[S["inv2"][p]]["status"] == "Paid" for p in ("sender", "recipient"))


def test_11_final_pdf_has_fee_rows():
    from pypdf import PdfReader
    r = requests.get(f"{API}/reports/{S['tid']}/final/pdf", headers=S["r"])
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "Sender 50% fee share" in text and "Recipient 50% fee share" in text, text[:1500]
    v = requests.get(f"{API}/reports/{S['tid']}/verification/pdf", headers=S["r"])
    assert v.status_code == 200
    vt = "".join(p.extract_text() for p in PdfReader(io.BytesIO(v.content)).pages)
    print("AML PDF:", vt[:900])
    assert "Sender wallet screening" in vt
    print("DEAL", S["ref"], S["tid"], S["se"], S["re"])
