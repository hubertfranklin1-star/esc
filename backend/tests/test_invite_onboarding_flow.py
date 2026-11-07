# Regression: invitation/onboarding gating, onboarding fee config, forensic doc gating (no emails sent)
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    if r.status_code != 200:
        pytest.skip(f"login failed for {email}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin():
    return _login("admin@vaultbridge.demo", "AdminDemo#2026")


@pytest.fixture(scope="module")
def recipient():
    return _login("recipient@vaultbridge.demo", "RecipientDemo#2026")


@pytest.fixture(scope="module")
def sender():
    return _login("sender@vaultbridge.demo", "SenderDemo#2026")


@pytest.fixture(scope="module")
def fresh_tx(admin):
    r = requests.post(f"{API}/transactions", headers=admin,
                      json={"usd_value": 235000, "sender_name": "TEST_Gate Sender", "recipient_name": "TEST_Gate Recipient"})
    assert r.status_code == 200
    return r.json()


# Fresh deal structure
def test_fresh_deal_has_10_steps(fresh_tx):
    assert len(fresh_tx["steps"]) == 10
    assert fresh_tx["current_step"] == 1
    assert fresh_tx["invitations_sent_at"] is None


# Join is blocked before invitation email
def test_join_before_invite_blocked(fresh_tx, sender):
    r = requests.post(f"{API}/transactions/{fresh_tx['id']}/actions/join", headers=sender,
                      json={"data": {"legal_name": "x", "contact_name": "x", "contact_email": "a@b.co",
                                     "wallet_address": "0x" + "a" * 40, "rules_accepted": True}})
    assert r.status_code == 400
    assert "invitation" in r.json()["detail"].lower()


# Invalid invite emails rejected (no email sent)
def test_invite_invalid_emails(fresh_tx, admin):
    r = requests.post(f"{API}/transactions/{fresh_tx['id']}/send-invitations", headers=admin,
                      json={"sender": "not-an-email", "recipient": "x"})
    assert r.status_code == 400


def test_invite_requires_admin(fresh_tx, sender):
    r = requests.post(f"{API}/transactions/{fresh_tx['id']}/send-invitations", headers=sender,
                      json={"sender": "delivered@resend.dev", "recipient": "delivered@resend.dev"})
    assert r.status_code == 403


# Step gating for admin actions
@pytest.mark.parametrize("action", ["approve_parties", "verify_deposit", "release_aml_report", "release"])
def test_admin_actions_gated_on_fresh_deal(fresh_tx, admin, action):
    r = requests.post(f"{API}/transactions/{fresh_tx['id']}/actions/{action}", headers=admin, json={"data": {}})
    assert r.status_code == 400


# Onboarding fee config
def test_onboarding_fee_get_and_validation(admin, sender):
    r = requests.get(f"{API}/onboarding-fee", headers=sender)
    assert r.status_code == 200 and isinstance(r.json()["amount_eth"], (int, float))
    assert requests.put(f"{API}/onboarding-fee", headers=sender, json={"amount_eth": 3}).status_code == 403
    assert requests.put(f"{API}/onboarding-fee", headers=admin, json={"amount_eth": -1}).status_code == 400


# Forensic docs hidden from parties before AML report release
def test_forensic_doc_gating(fresh_tx, admin, recipient):
    up = requests.post(f"{API}/reports/{fresh_tx['id']}/uploads", headers=admin,
                       data={"title": "TEST_gate doc", "category": "forensic"},
                       files={"file": ("TEST_gate.txt", b"gate", "text/plain")})
    assert up.status_code == 200
    doc_id = up.json()["id"]
    a = requests.get(f"{API}/reports/{fresh_tx['id']}/uploads?category=forensic", headers=admin)
    assert any(d["id"] == doc_id for d in a.json())
    rl = requests.get(f"{API}/reports/{fresh_tx['id']}/uploads?category=forensic", headers=recipient)
    assert rl.status_code == 200 and rl.json() == []
    assert requests.get(f"{API}/reports/uploads/{doc_id}/download", headers=recipient).status_code == 404
    assert requests.get(f"{API}/reports/uploads/{doc_id}/download", headers=admin).status_code == 200
