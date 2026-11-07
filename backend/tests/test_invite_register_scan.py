# Regression: invite-link registration (check-email/register), role conflict on deal creation, auto wallet scan on join
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
RUN = uuid.uuid4().hex[:6]
S_EMAIL = f"test_reg_s_{RUN}@resend.dev"
R_EMAIL = f"test_reg_r_{RUN}@resend.dev"
WALLET = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    if r.status_code != 200:
        pytest.skip(f"login failed for {email}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin():
    return _login("admin@vaultbridge.demo", "AdminDemo#2026")


@pytest.fixture(scope="module")
def deal(admin):
    r = requests.post(f"{API}/transactions", headers=admin, json={
        "usd_value": 250000, "sender_name": "TEST_Reg Sender Co", "recipient_name": "TEST_Reg Recipient Co",
        "sender_email": S_EMAIL, "recipient_email": R_EMAIL})
    assert r.status_code == 200, r.text
    tx = r.json()
    assert tx["invitations_sent_at"]
    assert tx["sender_user_id"] is None and tx["recipient_user_id"] is None
    return tx


@pytest.fixture(scope="module")
def state():
    return {}


# check-email
def test_check_email_unknown_and_existing():
    for e in ("nobody_" + RUN + "@resend.dev", "admin@vaultbridge.demo", "SENDER@vaultbridge.demo"):
        r = requests.post(f"{API}/auth/check-email", json={"email": e})
        assert r.status_code == 200
        assert r.json() == {"next": "login"}


def test_check_email_invited(deal):
    r = requests.post(f"{API}/auth/check-email", json={"email": S_EMAIL.upper()})
    assert r.json() == {"next": "register", "role": "sender"}
    r = requests.post(f"{API}/auth/check-email", json={"email": R_EMAIL})
    assert r.json() == {"next": "register", "role": "recipient"}


# register validation
def test_register_short_password(deal):
    r = requests.post(f"{API}/auth/register", json={"email": S_EMAIL, "password": "short", "name": "X"})
    assert r.status_code == 400
    assert "8" in r.json()["detail"]


def test_register_uninvited():
    r = requests.post(f"{API}/auth/register", json={"email": f"uninv_{RUN}@resend.dev", "password": "Password123", "name": "X"})
    assert r.status_code == 400
    assert "invited" in r.json()["detail"].lower()


def test_register_existing_demo_email():
    r = requests.post(f"{API}/auth/register", json={"email": "sender@vaultbridge.demo", "password": "Password123", "name": "X"})
    assert r.status_code == 400


# register success + twice
def test_register_sender_and_recipient(deal, state):
    for key, email, role in (("s", S_EMAIL, "sender"), ("r", R_EMAIL, "recipient")):
        r = requests.post(f"{API}/auth/register", json={"email": email, "password": "TestPass#2026", "name": f"TEST {role}"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["user"]["role"] == role and d["user"]["email"] == email
        state[key] = {"Authorization": f"Bearer {d['token']}"}
        r2 = requests.post(f"{API}/auth/register", json={"email": email, "password": "TestPass#2026", "name": "dup"})
        assert r2.status_code == 400
        assert requests.post(f"{API}/auth/check-email", json={"email": email}).json() == {"next": "login"}
        assert requests.post(f"{API}/auth/login", json={"email": email, "password": "TestPass#2026"}).status_code == 200


def test_new_users_see_only_invited_deal(deal, state):
    for key in ("s", "r"):
        r = requests.get(f"{API}/transactions", headers=state[key])
        assert r.status_code == 200
        txs = r.json()
        assert [t["id"] for t in txs] == [deal["id"]]


# role conflict on deal creation
def test_create_deal_role_conflict_and_no_orphan(admin):
    before = len(requests.get(f"{API}/transactions", headers=admin).json())
    r = requests.post(f"{API}/transactions", headers=admin, json={
        "usd_value": 100000, "sender_name": "TEST_Conflict S", "recipient_name": "TEST_Conflict R",
        "sender_email": "admin@vaultbridge.demo", "recipient_email": f"test_conf_{RUN}@resend.dev"})
    assert r.status_code == 400
    assert "admin" in r.json()["detail"]
    after = len(requests.get(f"{API}/transactions", headers=admin).json())
    # a rejected creation should not leave an orphan deal behind
    assert after == before, f"orphan deal created on 400: before={before} after={after}"


# join -> auto scan -> fees -> approve
def test_join_triggers_scan_and_approve(deal, state, admin):
    for key in ("s", "r"):
        r = requests.post(f"{API}/transactions/{deal['id']}/actions/join", headers=state[key], json={"data": {
            "legal_name": "TEST Co", "contact_name": "TEST", "contact_email": "a@resend.dev",
            "wallet_address": WALLET, "rules_accepted": True}})
        assert r.status_code == 200, r.text
        party = "sender" if key == "s" else "recipient"
        assert r.json()["onboarding"][party]["scan"]["status"] in ("running", "done")
    tx = None
    for _ in range(20):
        tx = requests.get(f"{API}/transactions/{deal['id']}", headers=admin).json()
        if all(tx["onboarding"][p].get("scan", {}).get("status") in ("done", "failed") for p in ("sender", "recipient")):
            break
        time.sleep(1)
    for p in ("sender", "recipient"):
        s = tx["onboarding"][p]["scan"]
        assert s["status"] == "done", s
        assert s["band"] and isinstance(s["score"], int) and s["scan_id"]
        pdf = requests.get(f"{API}/forensics/scans/{s['scan_id']}/pdf", headers=admin)
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    # rescan
    r = requests.post(f"{API}/transactions/{deal['id']}/actions/rescan_wallet", headers=admin, json={"data": {"party": "sender"}})
    assert r.status_code == 200 and r.json()["onboarding"]["sender"]["scan"]["status"] == "running"
    r = requests.post(f"{API}/transactions/{deal['id']}/actions/rescan_wallet", headers=state["s"], json={"data": {"party": "sender"}})
    assert r.status_code in (400, 403)
    # pay onboarding fees
    for key, p in (("s", "sender"), ("r", "recipient")):
        inv_id = tx["onboarding_fees"][p]["invoice_id"]
        r = requests.post(f"{API}/invoices/{inv_id}/pay", headers=state[key])
        assert r.status_code == 200, r.text
    tx = requests.get(f"{API}/transactions/{deal['id']}", headers=admin).json()
    assert tx["current_step"] == 4
    r = requests.post(f"{API}/transactions/{deal['id']}/actions/approve_parties", headers=admin, json={"data": {}})
    assert r.status_code == 200
    assert r.json()["current_step"] == 5
