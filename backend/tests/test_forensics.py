# Forensics (live Etherscan) API tests: auth, validation, scan, isolation, PDF
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
TORNADO = "0x8589427373D6D84E98730D7795D8f6f8731FDA16"
NORMAL = "0xab5801a7d398351b8be11c439e05c5b3259aec9b"
CREATED = []


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {email}")
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="module")
def admin():
    return login("admin@vaultbridge.demo", "AdminDemo#2026")


@pytest.fixture(scope="module")
def sender():
    return login("sender@vaultbridge.demo", "SenderDemo#2026")


@pytest.fixture(scope="module")
def recipient():
    return login("recipient@vaultbridge.demo", "RecipientDemo#2026")


@pytest.fixture(scope="module")
def tornado_scan(admin):
    r = admin.post(f"{API}/forensics/scan", json={"address": TORNADO, "label": "TEST_tornado"}, timeout=240)
    assert r.status_code == 200, r.text
    CREATED.append(r.json()["id"])
    return r.json()


@pytest.fixture(scope="module")
def normal_scan(sender):
    r = sender.post(f"{API}/forensics/scan", json={"address": NORMAL, "label": "TEST_normal"}, timeout=240)
    assert r.status_code == 200, r.text
    CREATED.append(r.json()["id"])
    return r.json()


# Auth
@pytest.mark.parametrize("method,path", [("post", "/forensics/scan"), ("get", "/forensics/scans"),
                                         ("get", "/forensics/scans/abc"), ("get", "/forensics/scans/abc/pdf")])
def test_unauth_401(method, path):
    r = getattr(requests, method)(f"{API}{path}", json={"address": NORMAL}, timeout=30)
    assert r.status_code == 401


# Validation
@pytest.mark.parametrize("addr", ["0x123", "not-an-address", "", "0xZZ5801a7d398351b8be11c439e05c5b3259aec9b"])
def test_invalid_address_400(sender, addr):
    r = sender.post(f"{API}/forensics/scan", json={"address": addr}, timeout=30)
    assert r.status_code == 400
    assert "valid Ethereum address" in r.text


# Tornado Cash donation -> Severe
def test_tornado_severe(tornado_scan):
    rep = tornado_scan["report"]
    print("tornado risk", rep["risk"], rep["activity"], "list_size", rep["sanctions"]["list_size"])
    assert rep["address"] == TORNADO.lower()
    assert rep["risk"]["band"] == "Severe"
    assert rep["risk"]["score"] >= 80
    assert rep["risky_services"]["self"] == "Tornado Cash: Donation"
    assert rep["sanctions"]["listed"] is False
    assert rep["sanctions"]["list_size"] > 0
    assert tornado_scan["label"] == "TEST_tornado"


# Normal wallet -> Low, real data
def test_normal_low(normal_scan):
    rep = normal_scan["report"]
    print("normal risk", rep["risk"], rep["balance_eth"], rep["activity"])
    assert rep["risk"]["band"] == "Low", rep["risk"]
    assert isinstance(rep["balance_eth"], float)
    assert rep["activity"]["normal_tx"] > 0
    assert len(rep["recent_transactions"]) > 0
    assert rep["recent_transactions"][0]["hash"].startswith("0x")
    assert len(rep["counterparties"]) > 0
    assert "Etherscan" in rep["data_source"]
    assert "_id" not in normal_scan


# Persistence + isolation
def test_scan_get_persisted(sender, normal_scan):
    r = sender.get(f"{API}/forensics/scans/{normal_scan['id']}", timeout=30)
    assert r.status_code == 200
    assert r.json()["report"]["address"] == NORMAL.lower()


def test_list_isolation(admin, sender, recipient, normal_scan, tornado_scan):
    s_ids = [x["id"] for x in sender.get(f"{API}/forensics/scans", timeout=30).json()]
    r_ids = [x["id"] for x in recipient.get(f"{API}/forensics/scans", timeout=30).json()]
    a_ids = [x["id"] for x in admin.get(f"{API}/forensics/scans", timeout=30).json()]
    assert normal_scan["id"] in s_ids and tornado_scan["id"] not in s_ids
    assert normal_scan["id"] not in r_ids and tornado_scan["id"] not in r_ids
    assert normal_scan["id"] in a_ids and tornado_scan["id"] in a_ids


def test_cross_user_404(sender, recipient, tornado_scan, normal_scan):
    assert sender.get(f"{API}/forensics/scans/{tornado_scan['id']}", timeout=30).status_code == 404
    assert recipient.get(f"{API}/forensics/scans/{normal_scan['id']}", timeout=30).status_code == 404
    assert recipient.get(f"{API}/forensics/scans/{normal_scan['id']}/pdf", timeout=30).status_code == 404


def test_admin_can_get_other(admin, normal_scan):
    assert admin.get(f"{API}/forensics/scans/{normal_scan['id']}", timeout=30).status_code == 200


# PDF
def test_pdf(admin, tornado_scan):
    r = admin.get(f"{API}/forensics/scans/{tornado_scan['id']}/pdf", timeout=60)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    with open("/tmp/forensic_tornado.pdf", "wb") as f:
        f.write(r.content)


def test_ids_written():
    with open("/tmp/forensic_ids.txt", "w") as f:
        f.write("\n".join(CREATED))
