import asyncio
import base64
import hmac
import logging
import os
import re
import secrets
import uuid
from contextlib import suppress
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import DuplicateKeyError
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

try:
    from backend.pdf_reports import build_report, build_forensic_report
    from backend import forensics
    from backend.mailer import send_email, BRAND
except ModuleNotFoundError:
    from pdf_reports import build_report, build_forensic_report
    import forensics
    from mailer import send_email, BRAND
from html import escape
from urllib.parse import urlencode

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
JWT_SECRET = os.environ["JWT_SECRET"]
logger = logging.getLogger(__name__)

INDEXES = {
    "users": [IndexModel([("email", ASCENDING)], name="email", unique=True), IndexModel([("id", ASCENDING)], name="id", unique=True)],
    "transactions": [IndexModel([("id", ASCENDING)], name="id", unique=True), IndexModel([("reference", ASCENDING)], name="reference", unique=True)],
    "invoices": [IndexModel([("id", ASCENDING)], name="id", unique=True), IndexModel([("transaction_id", ASCENDING)], name="tx"),
                 IndexModel([("payment_tx_hash", ASCENDING)], name="payment_tx_hash", unique=True, partialFilterExpression={"payment_tx_hash": {"$type": "string"}})],
    "audit_logs": [IndexModel([("transaction_id", ASCENDING)], name="tx"), IndexModel([("timestamp", DESCENDING)], name="ts")],
    "notifications": [IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_ts")],
    "uploaded_reports": [IndexModel([("id", ASCENDING)], name="id", unique=True), IndexModel([("transaction_id", ASCENDING)], name="tx")],
    "cron_runs": [IndexModel([("id", ASCENDING)], name="id", unique=True), IndexModel([("at", ASCENDING)], name="ttl", expireAfterSeconds=86400)],
}

ETH_PRICE = 2350.0
REQUIRED_CONF = 12
CONF_INTERVAL = 2.0

FEE_CATALOG = [
    ("escrow_admin", "Escrow administration", 1500000, "recipient"),
    ("blockchain_analytics", "Blockchain analytics", 75000, "recipient"),
    ("compliance", "Compliance assessment", 150000, "recipient"),
    ("custody_admin", "Custody administration", 600000, "recipient"),
    ("settlement_admin", "Settlement administration", 300000, "recipient"),
]
ENGAGEMENT_ITEMS = ["escrow_admin", "blockchain_analytics", "compliance", "custody_admin", "settlement_admin"]

COMPLIANCE_CHECKS = [
    ("identity", "Identity verification"),
    ("company", "Company verification"),
    ("ubo", "Beneficial ownership"),
    ("sof", "Source-of-funds review"),
    ("sanctions", "Sanctions screening"),
    ("wallet_risk", "Wallet risk assessment"),
    ("tx_monitoring", "Transaction monitoring"),
]
COMPLIANCE_STATUSES = ["Pending", "Under Review", "More Info Needed", "Approved", "Rejected"]

STEPS = [
    ("Sender joins the deal", "sender"),
    ("Recipient joins the deal", "recipient"),
    ("Both parties pay the onboarding fee", "both"),
    ("Admin approves both parties & opens the escrow", "admin"),
    ("Sender deposits ETH into the escrow wallet", "sender"),
    ("Admin completes AML checks on the deposit", "admin"),
    ("Admin releases the AML report", "admin"),
    ("Recipient requests the funds", "recipient"),
    ("Both parties pay their half of the escrow fees", "both"),
    ("Admin releases funds to recipient", "admin"),
]
STATUS_BY_STEP = {
    1: "Awaiting onboarding", 2: "Awaiting onboarding", 3: "Awaiting onboarding fees", 4: "Awaiting approval",
    5: "Awaiting deposit", 6: "AML checks in progress", 7: "Preparing AML report", 8: "Funds held in escrow",
    9: "Escrow fees due", 10: "Release pending",
}
REPORT_TYPES = [
    ("agreement", "Escrow agreement", 4),
    ("deposit", "Deposit receipt", 5),
    ("verification", "AML verification report", 6),
    ("final", "Final settlement statement", 10),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def money(v: float) -> str:
    return f"${v:,.2f}"


def eth(v: float) -> str:
    return f"{v:,.6f} ETH"


app = FastAPI()
api = APIRouter(prefix="/api")


# ---------- auth ----------
def hash_pw(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def make_token(user: dict) -> str:
    payload = {"sub": user["id"], "role": user["role"], "exp": datetime.now(timezone.utc) + timedelta(hours=12)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def public_user(u: dict) -> dict:
    return {k: u[k] for k in ("id", "email", "name", "role", "organisation")}


async def current_user(request: Request) -> dict:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Not signed in")
    try:
        payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user:
        raise HTTPException(401, "User not found")
    return user


async def admin_user(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Administrator only")
    return user


class LoginIn(BaseModel):
    email: str
    password: str


@api.post("/auth/login")
async def login(body: LoginIn):
    user = await db.users.find_one({"email": body.email.strip().lower()}, {"_id": 0})
    if not user or not bcrypt.checkpw(body.password.encode(), user["password_hash"].encode()):
        raise HTTPException(401, "Invalid email or password")
    return {"token": make_token(user), "user": public_user(user)}


async def invited_role(email: str) -> Optional[str]:
    tx = await db.transactions.find_one({"$or": [{"invite_emails.sender": email}, {"invite_emails.recipient": email}], "invitations_sent_at": {"$ne": None}},
                                        {"_id": 0, "invite_emails": 1}, sort=[("created_at", DESCENDING)])
    if not tx:
        return None
    return "sender" if tx["invite_emails"]["sender"] == email else "recipient"


class EmailIn(BaseModel):
    email: str


@api.post("/auth/check-email")
async def check_email(body: EmailIn):
    email = body.email.strip().lower()
    if await db.users.find_one({"email": email}, {"_id": 1}):
        return {"next": "login"}
    role = await invited_role(email)
    return {"next": "register", "role": role} if role else {"next": "login"}


class RegisterIn(BaseModel):
    email: str
    password: str
    name: str


@api.post("/auth/register")
async def register(body: RegisterIn):
    email = body.email.strip().lower()
    need(len(body.password) >= 8, "Password must be at least 8 characters")
    need(bool(body.name.strip()), "Please enter your full name")
    need(not await db.users.find_one({"email": email}, {"_id": 1}), "An account with this email already exists — sign in instead")
    role = await invited_role(email)
    need(role is not None, "This email hasn't been invited to an escrow deal")
    tx = await db.transactions.find_one({f"invite_emails.{role}": email}, {"_id": 0}, sort=[("created_at", DESCENDING)])
    user = {"id": new_id(), "email": email, "password_hash": hash_pw(body.password), "role": role,
            "name": body.name.strip(), "organisation": tx[f"{role}_name"], "created_at": now(), "invited": True}
    await db.users.insert_one(dict(user))
    await db.transactions.update_many({f"invite_emails.{role}": email, f"onboarding.{role}.status": {"$in": ["not_started", "rejected"]}},
                                      {"$set": {f"{role}_user_id": user["id"], f"{role}_email": email}})
    async for t in db.transactions.find({f"{role}_user_id": user["id"]}, {"_id": 0}):
        await notify(t, [role], f"Welcome to escrow deal {t['reference']}",
                     "Your account is ready. Read the escrow rules and join the deal from Home.", "email")
    await log(tx, user, "Account created", f"{email} created a {role} account from the invitation")
    return {"token": make_token(user), "user": public_user(user)}


@api.get("/auth/me")
async def me(user: dict = Depends(current_user)):
    return public_user(user)


# ---------- helpers ----------
async def log(tx: Optional[dict], user: Optional[dict], action: str, detail: str = ""):
    await db.audit_logs.insert_one({
        "id": new_id(),
        "transaction_id": tx["id"] if tx else None,
        "reference": tx["reference"] if tx else None,
        "actor": user["email"] if user else "system",
        "actor_role": user["role"] if user else "system",
        "action": action,
        "detail": detail,
        "timestamp": now(),
    })


async def notify(tx: dict, targets: List[str], title: str, body: str, kind: str = "notification"):
    ids = []
    if "sender" in targets:
        ids.append(tx["sender_user_id"])
    if "recipient" in targets:
        ids.append(tx["recipient_user_id"])
    if "admin" in targets:
        ids += [u["id"] async for u in db.users.find({"role": "admin"}, {"id": 1})]
    docs = [{"id": new_id(), "user_id": i, "transaction_id": tx["id"], "reference": tx["reference"], "kind": kind,
             "title": title, "body": body, "read": False, "created_at": now()} for i in ids if i]
    if docs:
        await db.notifications.insert_many(docs)


def party_of(tx: dict, user: dict) -> Optional[str]:
    if user["role"] == "sender" and tx["sender_user_id"] == user["id"]:
        return "sender"
    if user["role"] == "recipient" and tx["recipient_user_id"] == user["id"]:
        return "recipient"
    return None


def joined(ob: dict) -> bool:
    return ob["status"] in ("submitted", "approved")


def step_flags(tx: dict) -> List[bool]:
    ob = tx["onboarding"]
    dep, st = tx["deposit"], tx["settlement"]
    of = tx.get("onboarding_fees", {})
    sf = tx.get("settlement_fees") or {}
    return [
        joined(ob["sender"]),
        joined(ob["recipient"]),
        all(of.get(p, {}).get("submitted_at") for p in ("sender", "recipient")),
        all(ob[p]["status"] == "approved" for p in ("sender", "recipient")),
        bool(dep.get("initiated_at")),
        bool(tx["aml"].get("completed_at")),
        bool(tx["aml"].get("report_released_at")),
        bool(st.get("requested_at")),
        all(sf.get(p, {}).get("submitted_at") for p in ("sender", "recipient")),
        bool(tx.get("completed_at")),
    ]


def current_step(tx: dict) -> int:
    for i, done in enumerate(step_flags(tx)):
        if not done:
            return i + 1
    return len(STEPS) + 1


def status_of(tx: dict) -> str:
    if tx.get("completed_at"):
        return "Completed"
    if tx.get("on_hold"):
        return "On hold"
    if any(tx["invitations"][p]["status"] == "declined" for p in ("sender", "recipient")):
        return "Invitation declined"
    step = current_step(tx)
    if step == 6 and not tx["deposit"].get("confirmed_at"):
        return "Deposit awaiting confirmation"
    return STATUS_BY_STEP.get(step, "In progress")


def present(tx: dict) -> dict:
    flags = step_flags(tx)
    out = {k: v for k, v in tx.items() if k != "_id"}
    out["steps"] = [{"n": i + 1, "title": t, "actor": a, "done": flags[i]} for i, (t, a) in enumerate(STEPS)]
    out["current_step"] = current_step(tx)
    out["status"] = status_of(tx)
    out["reports"] = [{"type": k, "title": t, "available": flags[s - 1]} for k, t, s in REPORT_TYPES]
    return out


async def refresh_deposit(tx: dict) -> dict:
    return tx


async def load_tx(tx_id: str, user: dict) -> dict:
    tx = await db.transactions.find_one({"id": tx_id}, {"_id": 0})
    if not tx or (user["role"] != "admin" and not party_of(tx, user)):
        raise HTTPException(404, "Transaction not found")
    return await refresh_deposit(tx)


def tx_scope(user: dict) -> dict:
    if user["role"] == "sender":
        return {"sender_user_id": user["id"]}
    if user["role"] == "recipient":
        return {"recipient_user_id": user["id"]}
    return {}


async def next_counter(name: str) -> int:
    doc = await db.counters.find_one_and_update({"name": name}, {"$inc": {"value": 1}}, upsert=True, return_document=True)
    return doc["value"]


async def new_transaction(reference: str, usd_value: float, sender_name: str, recipient_name: str, network: str, links: Optional[dict] = None, price: float = ETH_PRICE) -> dict:
    if links is None:  # first-run sample deal: link the sample party accounts when they exist
        links = {"invite_emails": {"sender": "", "recipient": ""}}
        for p in ("sender", "recipient"):
            u = await db.users.find_one({"role": p}, {"_id": 0})
            if u:
                links.update({f"{p}_user_id": u["id"], f"{p}_email": u["email"]})
                links["invite_emails"][p] = u["email"]
    qty = round(usd_value / price, 6)
    party = {"status": "pending", "responded_at": None}
    ob = {"status": "not_started", "data": {}, "submitted_at": None, "reviewed_at": None, "note": ""}
    tx = {
        "id": new_id(), "reference": reference, "asset": "ETH", "usd_value": usd_value, "eth_price": price,
        "eth_quantity": qty, "network": network, "sender_name": sender_name, "recipient_name": recipient_name,
        "sender_user_id": None, "recipient_user_id": None, "sender_email": "", "recipient_email": "",
        "escrow_vault_address": None, "created_at": now(), "invitations_sent_at": None,
        "invite_emails": {"sender": "", "recipient": ""},
        "invitations": {"sender": dict(party), "recipient": dict(party)},
        "onboarding": {"sender": dict(ob), "recipient": dict(ob)},
        "agreement": {"issued_at": None, "sender_accepted_at": None, "recipient_accepted_at": None},
        "payment": {"invoice_id": None, "submitted_at": None, "confirmed_at": None},
        "onboarding_fees": {p: {"invoice_id": None, "submitted_at": None, "confirmed_at": None} for p in ("sender", "recipient")},
        "deposit": {"initiated_at": None},
        "settlement_fees": {},
        "analysis": {}, "aml": {"completed_at": None},
        "compliance": {k: {"label": label, "status": "Pending", "note": "", "updated_at": now()} for k, label in COMPLIANCE_CHECKS},
        "report_access": {"sender": None, "recipient": None},
        "settlement": {"status": "none"}, "on_hold": False, "completed_at": None,
    }
    tx.update(links or {})
    await db.transactions.insert_one(dict(tx))
    return tx


def invite_html(tx: dict, p: str) -> str:
    link = os.environ["APP_URL"].rstrip("/") + "/login?" + urlencode({"email": tx["invite_emails"][p]})
    rules = ["Each party pays a one-time onboarding fee to open their escrow account.",
             f"The sender deposits {eth(tx['eth_quantity'])} into the escrow wallet; the transaction is checked on-chain.",
             "The deposit is AML-screened on-chain and the AML report is shared with both parties.",
             "The recipient requests the funds; the escrow fees are then split 50/50 and each party pays their half in ETH.",
             "The admin then releases the ETH to the recipient's wallet."]
    li = "".join(f"<li style='margin:4px 0'>{escape(r)}</li>" for r in rules)
    return (f"<table role='presentation' width='100%'><tr><td style='padding:24px;font-family:Arial,sans-serif;color:#0B111E'>"
            f"<h2 style='margin:0 0 12px'>You're invited to escrow deal {escape(tx['reference'])}</h2>"
            f"<p>{escape(tx[f'{p}_name'])} is invited to join as <b>{p}</b>.</p>"
            f"<table style='border-collapse:collapse;font-size:14px'>"
            f"<tr><td style='padding:4px 12px 4px 0;color:#64748B'>Sender</td><td>{escape(tx['sender_name'])}</td></tr>"
            f"<tr><td style='padding:4px 12px 4px 0;color:#64748B'>Recipient</td><td>{escape(tx['recipient_name'])}</td></tr>"
            f"<tr><td style='padding:4px 12px 4px 0;color:#64748B'>Deal value</td><td>{escape(money(tx['usd_value']))} ({escape(eth(tx['eth_quantity']))})</td></tr>"
            f"<tr><td style='padding:4px 12px 4px 0;color:#64748B'>Network</td><td>{escape(tx['network'])}</td></tr></table>"
            f"<h3 style='margin:18px 0 6px'>Escrow rules</h3><ol style='padding-left:18px;font-size:14px'>{li}</ol>"
            f"<p style='margin:20px 0'><a href='{link}' style='background:#0284C7;color:#fff;padding:12px 20px;border-radius:6px;text-decoration:none'>Enter the escrow</a></p>"
            f"<p style='font-size:12px;color:#888'>Sent by {BRAND}. Open the link and continue with this email address: if you're new you'll create your own account and password, otherwise just sign in. We will never ask you to share login or wallet secrets by email.</p>"
            f"</td></tr></table>")


class InviteEmailsIn(BaseModel):
    sender: str
    recipient: str


EMAIL_RE = r"[^@\s]+@[^@\s]+\.[^@\s]+"


async def invite_links(onboarding: Optional[dict], emails: dict) -> dict:
    need(all(re.fullmatch(EMAIL_RE, e) for e in emails.values()), "Enter valid email addresses for both parties")
    need(emails["sender"] != emails["recipient"], "Sender and recipient need different email addresses")
    links = {"invite_emails": emails}
    for p, e in emails.items():
        if onboarding and joined(onboarding[p]):
            continue
        existing = await db.users.find_one({"email": e}, {"_id": 0})
        need(not existing or existing["role"] == p, f"{e} is already registered as {existing['role'] if existing else ''} and can't be invited as {p}")
        links[f"{p}_user_id"] = existing["id"] if existing else None
        links[f"{p}_email"] = e
    return links


async def deliver_invites(tx: dict, emails: dict, user: dict):
    links = await invite_links(tx["onboarding"], emails)
    await db.transactions.update_one({"id": tx["id"]}, {"$set": links})
    tx = {**tx, **links}
    sent = []
    for p, e in emails.items():
        if joined(tx["onboarding"][p]):
            continue
        await send_email(to=e, subject=f"Invitation to escrow deal {tx['reference']} — {BRAND}", html=invite_html(tx, p))
        sent.append(p)
        await db.transactions.update_one({"id": tx["id"]}, {"$set": {"invitations_sent_at": now(), f"invitations.{p}.emailed_at": now()}})
        await notify(tx, [p], f"You're invited to escrow deal {tx['reference']}",
                     f"Invitation email sent to {e}. Read the rules and enter the escrow from Home.", "email")
    need(bool(sent), "Both parties have already joined")
    await log(tx, user, "Invitation emails sent", " · ".join(f"{p}: {emails[p]}" for p in sent))


@api.post("/transactions/{tx_id}/send-invitations")
async def send_invitations(tx_id: str, body: InviteEmailsIn, user: dict = Depends(admin_user)):
    tx = await load_tx(tx_id, user)
    need(not tx.get("completed_at"), "This deal is already completed")
    await deliver_invites(tx, {"sender": body.sender.strip().lower(), "recipient": body.recipient.strip().lower()}, user)
    return present(await load_tx(tx_id, user))


# ---------- ETH price: saved every 5 minutes from free public sources ----------
PRICE_REFRESH_SECONDS = 300
price_tasks: set = set()


def price_age(doc: dict) -> float:
    return (datetime.now(timezone.utc) - datetime.fromisoformat(doc["fetched_at"])).total_seconds()


async def refresh_eth_price(min_gap: int = 60) -> Optional[dict]:
    doc = await db.settings.find_one({"key": "eth_price"}, {"_id": 0})
    if doc and doc.get("usd") and doc.get("fetched_at") and price_age(doc) < min_gap:
        return doc  # just refreshed (the 5- and 15-minute schedules overlap)
    try:
        usd, source = await forensics.eth_price()
    except Exception as e:
        logger.warning("ETH price refresh failed, keeping the saved price: %s", e)
        await db.settings.update_one({"key": "eth_price"}, {"$set": {"last_error": str(e)[:200], "last_error_at": now()}}, upsert=True)
        return None
    fresh = {"usd": round(usd, 2), "source": source, "fetched_at": now(), "last_error": None}
    await db.settings.update_one({"key": "eth_price"}, {"$set": fresh}, upsert=True)
    return fresh


def refresh_price_soon():
    if not price_tasks:
        t = asyncio.create_task(refresh_eth_price())
        price_tasks.add(t)
        t.add_done_callback(price_tasks.discard)


async def saved_eth_price() -> dict:
    """The ETH price the app uses: the copy saved by the 5-minute schedule, whether the price services are up or down."""
    doc = await db.settings.find_one({"key": "eth_price"}, {"_id": 0})
    if doc and doc.get("usd") and doc.get("fetched_at"):
        if price_age(doc) > PRICE_REFRESH_SECONDS:
            refresh_price_soon()  # catches up where the schedule runs less often; this request still uses the saved price
        return doc
    doc = await refresh_eth_price(min_gap=0)  # nothing saved yet (very first start)
    if not doc:
        raise HTTPException(503, "The ETH price hasn't been saved yet — try again in a minute")
    return doc


@api.get("/eth-price")
async def get_eth_price(user: dict = Depends(current_user)):
    doc = await saved_eth_price()
    return {"usd": doc["usd"], "source": doc["source"], "fetched_at": doc["fetched_at"], "refresh_minutes": PRICE_REFRESH_SECONDS // 60}


@api.post("/cron/eth-price")
async def cron_eth_price(request: Request):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    auth = request.headers.get("authorization", "")
    if not secret or not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:].encode(), secret.encode()):
        raise HTTPException(401, "Unauthorized")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid request body")
    if not isinstance(body, dict):
        raise HTTPException(400, "Invalid request body")
    run_id = str(request.headers.get("x-webhook-id") or body.get("run_id") or new_id())
    try:
        await db.cron_runs.insert_one({"id": run_id, "job": "eth-price", "at": datetime.now(timezone.utc)})
    except DuplicateKeyError:
        return {"ok": True, "duplicate": True}
    refresh_price_soon()
    return {"ok": True}


# ---------- transactions ----------
class TxCreate(BaseModel):
    usd_value: float
    sender_name: str
    recipient_name: str
    sender_email: str
    recipient_email: str
    network: str = "Ethereum Mainnet"


@api.get("/transactions")
async def list_transactions(user: dict = Depends(current_user)):
    txs = await db.transactions.find(tx_scope(user), {"_id": 0}).sort("created_at", ASCENDING).to_list(200)
    return [present(await refresh_deposit(t)) for t in txs]


@api.post("/transactions")
async def create_transaction(body: TxCreate, user: dict = Depends(admin_user)):
    if body.usd_value <= 0 or not body.sender_name.strip() or not body.recipient_name.strip():
        raise HTTPException(400, "Value and party names are required")
    emails = {"sender": body.sender_email.strip().lower(), "recipient": body.recipient_email.strip().lower()}
    links = await invite_links(None, emails)
    p = await saved_eth_price()
    price = p["usd"]
    links.update({"eth_price_source": p["source"], "eth_price_at": p["fetched_at"]})
    n = await db.transactions.count_documents({}) + 1
    ref = f"TSX-ETH-2026-{n:03d}"
    while await db.transactions.find_one({"reference": ref}):
        n += 1
        ref = f"TSX-ETH-2026-{n:03d}"
    tx = await new_transaction(ref, body.usd_value, body.sender_name.strip(), body.recipient_name.strip(), body.network, links, price)
    await log(tx, user, "Deal created", f"{ref} — deal value {money(body.usd_value)}")
    await deliver_invites(tx, emails, user)
    return present(await load_tx(tx["id"], user))


@api.get("/transactions/{tx_id}")
async def get_transaction(tx_id: str, user: dict = Depends(current_user)):
    return present(await load_tx(tx_id, user))


class ActionIn(BaseModel):
    data: Dict[str, Any] = {}


def need(cond: bool, msg: str):
    if not cond:
        raise HTTPException(403 if " only" in msg.lower() or msg.lower().startswith("only") else 400, msg)


@api.post("/transactions/{tx_id}/actions/{action}")
async def run_action(tx_id: str, action: str, body: ActionIn, user: dict = Depends(current_user)):
    tx = await load_tx(tx_id, user)
    d = body.data or {}
    is_admin = user["role"] == "admin"
    party = party_of(tx, user)
    step = current_step(tx)
    sets: Dict[str, Any] = {}
    scan_party = None
    need(not tx.get("completed_at"), "This deal is already completed")
    if action not in ("hold", "resume"):
        need(not tx.get("on_hold"), "This deal is on hold — an admin must resume it")

    if action == "resend_invitation":
        need(is_admin, "Administrator only")
        p = d.get("party")
        need(p in ("sender", "recipient") and tx["invitations"][p]["status"] == "declined", "No declined invitation for that party")
        sets[f"invitations.{p}"] = {"status": "pending", "responded_at": None}
        await notify(tx, [p], f"Invitation re-sent — {tx['reference']}", "The admin has re-sent your escrow invitation.", "email")
        msg = f"Invitation re-sent to {p}"
    elif action == "join":
        need(party is not None, "Only an invited party can join")
        need(bool(tx.get("invitations_sent_at")), "The admin hasn't sent your invitation email yet")
        need(tx["invitations"][party]["status"] != "declined", "You declined this invitation")
        need(tx["onboarding"][party]["status"] in ("not_started", "rejected"), "You have already joined this deal")
        required = ["legal_name", "contact_name", "contact_email", "wallet_address"]
        need(all(str(d.get(k, "")).strip() for k in required), "Please fill in all fields")
        w = str(d["wallet_address"]).strip()
        need(w.startswith("0x") and len(w) == 42 and all(c in "0123456789abcdefABCDEF" for c in w[2:]), "Wallet address must be 0x followed by 40 hex characters")
        need(bool(d.get("rules_accepted")), "Please read and accept the escrow rules")
        data = {k: str(d.get(k, "")).strip() for k in required}
        sets[f"invitations.{party}"] = {"status": "accepted", "responded_at": now()}
        sets[f"onboarding.{party}"] = {"status": "submitted", "data": data, "submitted_at": now(), "reviewed_at": None, "note": ""}
        if not tx.get("onboarding_fees", {}).get(party, {}).get("invoice_id"):
            fee = await onboarding_fee_eth()
            inv = await make_invoice(tx, party, [{"code": "onboarding", "label": "Escrow onboarding fee", "amount": fee}], "onboarding", currency="ETH")
            sets[f"onboarding_fees.{party}"] = {"invoice_id": inv["id"], "submitted_at": None, "confirmed_at": None}
        await notify(tx, ["admin"], f"{party.capitalize()} joined the deal", f"{tx['reference']}: {data['legal_name']} joined as {party} and is waiting for approval.")
        scan_party = party
        msg = f"{party.capitalize()} joined the deal"
    elif action == "rescan_wallet":
        need(is_admin, "Administrator only")
        scan_party = d.get("party")
        need(scan_party in ("sender", "recipient") and joined(tx["onboarding"][scan_party]), "That party hasn't joined yet")
        sets[f"onboarding.{scan_party}.scan"] = {"status": "running", "started_at": now()}
        msg = f"Wallet scan restarted for {scan_party}"
    elif action == "decline":
        need(party is not None, "Only an invited party can decline")
        need(tx["invitations"][party]["status"] == "pending", "Invitation already answered")
        sets[f"invitations.{party}"] = {"status": "declined", "responded_at": now()}
        await notify(tx, ["admin"], f"Invitation declined by {party}", f"{tx['reference']}: the {party} declined the invitation.")
        msg = f"{party.capitalize()} declined the invitation"
    elif action == "approve_parties":
        need(is_admin, "Administrator only")
        need(step == 4, "Both parties must join and pay the onboarding fee first")
        escrow = await fee_wallet()
        need(bool(escrow), "Set your receiving wallet on the Payments page first")
        sets["escrow_vault_address"] = escrow
        for p in ("sender", "recipient"):
            sets[f"onboarding.{p}.status"] = "approved"
            sets[f"onboarding.{p}.reviewed_at"] = now()
            sets[f"onboarding_fees.{p}.confirmed_at"] = now()
            await db.invoices.update_one({"id": tx["onboarding_fees"][p]["invoice_id"], "status": "Payment Sent"}, {"$set": {"status": "Paid", "paid_at": now()}})
        sets["agreement"] = {"issued_at": now(), "sender_accepted_at": tx["onboarding"]["sender"]["submitted_at"], "recipient_accepted_at": tx["onboarding"]["recipient"]["submitted_at"]}
        await notify(tx, ["sender", "recipient"], "Escrow account open", f"{tx['reference']}: you're approved and the escrow is open. The sender can now deposit the ETH.")
        msg = "Both parties approved; escrow opened"
    elif action == "reject_party":
        need(is_admin, "Administrator only")
        p = d.get("party")
        need(p in ("sender", "recipient") and tx["onboarding"][p]["status"] == "submitted", "That party is not waiting for approval")
        sets[f"onboarding.{p}.status"] = "rejected"
        sets[f"onboarding.{p}.note"] = str(d.get("note", ""))
        await notify(tx, [p], "Please update your details", f"{tx['reference']}: the admin asked you to update your details. {d.get('note', '')}")
        msg = f"Asked {p} to update their details"
    elif action == "deposit":
        need(party == "sender", "Only the sender can deposit")
        need(step == 5, "Deposit is not open yet")
        escrow = tx.get("escrow_vault_address")
        need(bool(escrow), "The escrow wallet isn't set yet")
        h = str(d.get("tx_hash", "")).strip()
        dep = {"initiated_at": now(), "from_address": tx["onboarding"]["sender"]["data"]["wallet_address"], "to_address": escrow,
               "eth_quantity": tx["eth_quantity"], "tx_hash": None, "block_number": None, "verified_onchain": False, "confirmed_at": None}
        if h:
            chk = await chain_check(h, escrow, tx["eth_quantity"], tx["agreement"]["issued_at"], "deposit")
            dep.update({"tx_hash": h.lower(), "block_number": chk["block"], "from_address": chk["from"], "verified_onchain": True, "confirmed_at": now()})
        sets["deposit"] = dep
        await notify(tx, ["recipient", "admin"], "ETH deposit sent", f"{tx['reference']}: the sender deposited {eth(tx['eth_quantity'])} into escrow"
                     + (" — verified on-chain." if h else " — waiting for the admin to confirm it arrived."))
        msg = f"Deposit of {eth(tx['eth_quantity'])} sent to escrow"
    elif action == "verify_deposit":
        need(is_admin, "Administrator only")
        need(step == 6, "There is no deposit to check yet")
        need(not any(c["status"] in ("Rejected", "More Info Needed") for c in tx["compliance"].values()), "Resolve checks marked Rejected or More Info Needed first")
        sc = tx["onboarding"]["sender"].get("scan") or {}
        sets["analysis"] = {"generated_at": now(), "risk_score": sc.get("score"), "risk_band": sc.get("band") or {"running": "Scan in progress", "failed": "Scan failed"}.get(sc.get("status"), "Not scanned"),
                            "sanctioned": sc.get("sanctioned"), "scan_id": sc.get("scan_id")}
        if not tx["deposit"].get("confirmed_at"):
            sets["deposit.confirmed_at"] = now()
        for k, c in tx["compliance"].items():
            sets[f"compliance.{k}"] = {**c, "status": "Approved", "updated_at": now()}
        sets["aml.completed_at"] = now()
        await notify(tx, ["sender", "recipient"], "AML checks passed", f"{tx['reference']}: the deposit passed all AML checks and is held in escrow. The AML report will be released shortly.")
        msg = "AML checks completed — all checks approved"
    elif action == "set_compliance":
        need(is_admin, "Administrator only")
        k, s = d.get("check"), d.get("status")
        need(k in tx["compliance"] and s in COMPLIANCE_STATUSES, "Invalid check update")
        need(not tx["aml"].get("completed_at"), "Checks are already completed")
        sets[f"compliance.{k}"] = {"label": tx["compliance"][k]["label"], "status": s, "note": str(d.get("note", "")), "updated_at": now()}
        msg = f"{tx['compliance'][k]['label']} set to {s}"
    elif action == "release_aml_report":
        need(is_admin, "Administrator only")
        need(step == 7, "AML checks must be completed first")
        need(await db.uploaded_reports.count_documents({"transaction_id": tx["id"], "category": "forensic"}) > 0, "Upload at least one AML / forensic document on the Forensics page first")
        sets["aml.report_released_at"] = now()
        await notify(tx, ["sender", "recipient"], "AML report released", f"{tx['reference']}: the AML report is available on the Forensics page. The recipient can now request the funds.")
        msg = "AML report released to the parties"
    elif action == "request_release":
        need(party == "recipient", "Only the recipient can request the funds")
        need(step == 8, "Funds cannot be requested yet")
        need(bool(await fee_wallet()), "The admin hasn't set the payment wallet yet")
        saved = await saved_eth_price()
        price = saved["usd"]
        fees = [f for f in (await db.settings.find_one({"key": "fees"}))["items"] if f["code"] in ENGAGEMENT_ITEMS]
        half_usd = sum(f["amount"] for f in fees) / 2
        share = {}
        for p in ("sender", "recipient"):
            lines = [{"code": f["code"], "label": f"{f['label']} (50% share)", "amount": round(f["amount"] / 2 / price, 6)} for f in fees]
            inv = await make_invoice(tx, p, lines, "engagement", currency="ETH", extra={"usd_amount": half_usd, "eth_price": price})
            share[p] = {"invoice_id": inv["id"], "usd_amount": half_usd, "eth_amount": inv["amount"], "submitted_at": None, "confirmed_at": None}
        sets["settlement_fees"] = share
        sets["settlement_fee_price"] = {"eth_usd": price, "priced_at": now(), "price_saved_at": saved["fetched_at"], "source": saved["source"]}
        sets["settlement"] = {"status": "requested", "requested_at": now(), "requested_by": user["email"], "release_eth": tx["eth_quantity"]}
        await notify(tx, ["admin", "sender", "recipient"], "Escrow fees due — 50/50 split",
                     f"{tx['reference']}: the recipient requested the funds. Each party now pays {money(half_usd)} ({eth(share['sender']['eth_amount'])} at {money(price)}/ETH).")
        msg = "Recipient requested the funds"
    elif action == "release":
        need(is_admin, "Administrator only")
        need(step == 10, "Both parties must pay their half of the escrow fees first")
        sf = tx["settlement_fees"]
        if d.get("decision") == "approved":
            need(all(sf[p].get("confirmed_at") for p in ("sender", "recipient")), "Confirm that both fee payments reached your wallet first")
            ts = now()
            h = str(d.get("tx_hash", "")).strip()
            chk = await chain_check(h, tx["onboarding"]["recipient"]["data"]["wallet_address"], tx["eth_quantity"], tx["settlement"]["requested_at"], "release amount") if h else None
            for p in ("sender", "recipient"):
                await db.invoices.update_one({"id": sf[p]["invoice_id"], "status": "Payment Sent"}, {"$set": {"status": "Paid", "paid_at": ts}})
                sets[f"settlement_fees.{p}.confirmed_at"] = sf[p].get("confirmed_at") or ts
            sets.update({"settlement.status": "released", "settlement.approved_at": ts, "settlement.credited_at": ts,
                         "settlement.release_tx_hash": h.lower() if h else None, "settlement.release_block": chk["block"] if chk else None,
                         "settlement.release_verified": bool(chk), "completed_at": ts})
            await notify(tx, ["sender", "recipient"], "Funds released — deal completed", f"{tx['reference']}: {eth(tx['eth_quantity'])} was released to the recipient.")
            msg = "Funds released to recipient — deal completed"
        else:
            sets["settlement"] = {"status": "rejected", "rejected_at": now(), "note": str(d.get("note", ""))}
            sets["settlement_fees"] = {}
            for p in ("sender", "recipient"):
                await db.invoices.update_one({"id": sf[p]["invoice_id"], "status": {"$ne": "Paid"}}, {"$set": {"status": "Cancelled"}})
            await notify(tx, ["sender", "recipient"], "Release request declined", f"{tx['reference']}: the release request was declined. {d.get('note', '')}")
            msg = "Release request declined"
    elif action in ("hold", "resume"):
        need(is_admin, "Administrator only")
        sets["on_hold"] = action == "hold"
        msg = "Deal placed on hold" if action == "hold" else "Deal resumed"
    else:
        raise HTTPException(400, "Unknown action")

    if scan_party and action == "join":
        sets[f"onboarding.{scan_party}"]["scan"] = {"status": "running", "started_at": now()}
    await db.transactions.update_one({"id": tx_id}, {"$set": sets})
    await log(tx, user, msg, str(d.get("note", "")) if d.get("note") else "")
    if scan_party:
        wallet = d["wallet_address"].strip() if action == "join" else tx["onboarding"][scan_party]["data"]["wallet_address"]
        scan_tasks.add(t := asyncio.create_task(auto_scan(tx, scan_party, wallet)))
        t.add_done_callback(scan_tasks.discard)
    return present(await load_tx(tx_id, user))


scan_tasks: set = set()


async def auto_scan(tx: dict, party: str, wallet: str):
    key = f"onboarding.{party}.scan"
    try:
        report = await forensics.analyse(wallet)
    except Exception as e:
        logger.error("auto wallet scan failed: %s", e)
        await db.transactions.update_one({"id": tx["id"]}, {"$set": {key: {"status": "failed", "error": str(e)[:200], "finished_at": now()}}})
        return
    if not await db.transactions.find_one({"id": tx["id"]}, {"_id": 1}):
        return  # the deal was deleted while the scan ran — leave no trace
    doc = {"id": new_id(), "label": f"{tx['reference']} · {party} wallet (on join)", "report": report, "created_at": now(),
           "created_by": "system", "user_id": None, "transaction_id": tx["id"]}
    await db.forensic_scans.insert_one(dict(doc))
    r = report["risk"]
    await db.transactions.update_one({"id": tx["id"]}, {"$set": {key: {
        "status": "done", "scan_id": doc["id"], "band": r["band"], "score": r["score"], "sanctioned": report["sanctions"]["listed"],
        "balance_eth": report["balance_eth"], "finished_at": now()}}})
    await log(tx, None, "Wallet scan on join", f"{party} {wallet} — risk {r['band']} ({r['score']}/100)")
    await notify(tx, ["admin"], f"{party.capitalize()} wallet scanned", f"{tx['reference']}: risk {r['band']} ({r['score']}/100)"
                 + (" — SANCTIONS MATCH" if report["sanctions"]["listed"] else ""))


# ---------- fees & invoices ----------
@api.get("/fees")
async def get_fees(user: dict = Depends(current_user)):
    doc = await db.settings.find_one({"key": "fees"}, {"_id": 0})
    return doc["items"]


class FeeItem(BaseModel):
    code: str
    label: str
    amount: float
    party: str


@api.put("/fees")
async def put_fees(items: List[FeeItem], user: dict = Depends(admin_user)):
    codes = {c for c, *_ in FEE_CATALOG}
    need(all(i.code in codes and i.amount >= 0 and i.party in ("sender", "recipient") for i in items), "Invalid fee configuration")
    data = [i.model_dump() for i in items]
    await db.settings.update_one({"key": "fees"}, {"$set": {"items": data}}, upsert=True)
    await log(None, user, "Fees updated", ", ".join(f"{i.label}: ${i.amount:,.0f}" for i in items))
    return data


class InvoiceIn(BaseModel):
    transaction_id: str
    party: str
    kind: str = "standard"
    items: List[str]


def clean_invoice(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_id"}


@api.get("/invoices")
async def list_invoices(transaction_id: Optional[str] = None, user: dict = Depends(current_user)):
    q: Dict[str, Any] = {}
    if transaction_id:
        q["transaction_id"] = transaction_id
    if user["role"] != "admin":
        q["responsible_user_id"] = user["id"]
    return await db.invoices.find(q, {"_id": 0}).sort("issued_at", DESCENDING).to_list(500)


def amt(inv: dict) -> str:
    return eth(inv["amount"]) if inv.get("currency") == "ETH" else money(inv["amount"])


async def onboarding_fee_eth() -> float:
    doc = await db.settings.find_one({"key": "onboarding_fee"})
    return doc["amount_eth"] if doc else 2.0


async def fee_wallet() -> str:
    doc = await db.settings.find_one({"key": "onboarding_fee"})
    return (doc or {}).get("wallet", "")


class OnboardingFeeIn(BaseModel):
    amount_eth: float
    wallet: Optional[str] = None


@api.get("/onboarding-fee")
async def get_onboarding_fee(user: dict = Depends(current_user)):
    return {"amount_eth": await onboarding_fee_eth(), "wallet": await fee_wallet()}


@api.put("/onboarding-fee")
async def put_onboarding_fee(body: OnboardingFeeIn, user: dict = Depends(admin_user)):
    need(0 < body.amount_eth <= 1000, "Onboarding fee must be more than 0 and at most 1,000 ETH")
    sets = {"amount_eth": body.amount_eth}
    if body.wallet is not None:
        w = body.wallet.strip()
        need(forensics.valid(w), "Payment wallet must be 0x followed by 40 hex characters")
        sets["wallet"] = w
    await db.settings.update_one({"key": "onboarding_fee"}, {"$set": sets}, upsert=True)
    await log(None, user, "Onboarding fee updated", eth(body.amount_eth) + (f" — pay to {sets['wallet']}" if "wallet" in sets else ""))
    return {"amount_eth": body.amount_eth, "wallet": await fee_wallet()}


async def make_invoice(tx: dict, party: str, fee_items: List[dict], kind: str, user: Optional[dict] = None, currency: str = "USD", extra: Optional[dict] = None) -> dict:
    n = await next_counter("invoice")
    lines = [{"code": f["code"], "description": f["label"], "amount": f["amount"]} for f in fee_items]
    inv = {
        "id": new_id(), "invoice_number": f"TSX-INV-2026-{n:04d}", "transaction_id": tx["id"], "reference": tx["reference"],
        "kind": kind, "party": party,
        "responsible_name": tx[f"{party}_name"], "responsible_user_id": tx[f"{party}_user_id"],
        "items": lines, "amount": round(sum(line["amount"] for line in lines), 6), "currency": currency,
        "status": "Unpaid", "issued_at": now(), "submitted_at": None, "paid_at": None, **(extra or {}),
    }
    await db.invoices.insert_one(dict(inv))
    await notify(tx, [party], f"New invoice {inv['invoice_number']}", f"{tx['reference']}: an invoice for {amt(inv)} is ready. Open Home or Payments to pay it.")
    await log(tx, user, f"Invoice {inv['invoice_number']} issued", f"{ {'engagement': 'Escrow fee', 'onboarding': 'Onboarding fee'}.get(kind, 'Invoice')} to {party} — {amt(inv)}")
    return inv


@api.post("/invoices")
async def create_invoice(body: InvoiceIn, user: dict = Depends(admin_user)):
    tx = await load_tx(body.transaction_id, user)
    need(body.party in ("sender", "recipient") and body.items, "Choose a party and at least one fee")
    need(not tx.get("on_hold") and not tx.get("completed_at"), "This deal is not open for invoicing")
    fees = {i["code"]: i for i in (await db.settings.find_one({"key": "fees"}))["items"]}
    need(all(c in fees for c in body.items), "Unknown fee item")
    return await make_invoice(tx, body.party, [fees[c] for c in body.items], "standard", user)


async def load_invoice(inv_id: str, user: dict) -> dict:
    inv = await db.invoices.find_one({"id": inv_id}, {"_id": 0})
    if not inv or (user["role"] != "admin" and inv["responsible_user_id"] != user["id"]):
        raise HTTPException(404, "Invoice not found")
    return inv


class PayIn(BaseModel):
    tx_hash: str = ""


FEE_KEY = {"onboarding": "onboarding_fees", "engagement": "settlement_fees"}
FEE_LABEL = {"onboarding": "Onboarding fee", "engagement": "Escrow fee share"}


async def hash_used(h: str) -> bool:
    h = h.lower()
    return bool(await db.invoices.find_one({"payment_tx_hash": h}, {"_id": 1})
                or await db.transactions.find_one({"$or": [{"deposit.tx_hash": h}, {"settlement.release_tx_hash": h}]}, {"_id": 1}))


async def chain_check(h: str, to: str, amount: float, not_before: str, what: str = "fee") -> dict:
    need(bool(forensics.TX_HASH.fullmatch(h)), "Transaction hash must be 0x followed by 64 hex characters")
    need(not await hash_used(h), "This transaction has already been used for a payment")
    try:
        return await forensics.verify_payment(h, to, amount, datetime.fromisoformat(not_before), what)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("payment verification failed: %s", e)
        raise HTTPException(503, "Couldn't reach the Ethereum network to check the payment — try again shortly")


def others(inv: dict) -> List[str]:
    return ["admin"] + (["recipient" if inv["party"] == "sender" else "sender"] if inv["kind"] == "engagement" else [])


async def verify_invoice_payment(inv: dict, tx: dict, user: dict, h: str, wallet: str):
    chk = await chain_check(h, wallet, inv["amount"], inv["issued_at"])
    ts = now()
    party_wallet = tx["onboarding"][inv["party"]]["data"].get("wallet_address", "")
    from_match = chk["from"].lower() == party_wallet.lower()
    try:
        res = await db.invoices.update_one({"id": inv["id"], "status": "Unpaid"}, {"$set": {
            "status": "Paid", "submitted_at": ts, "paid_at": ts, "payment_ref": h, "payment_tx_hash": h.lower(), "payment_to": wallet,
            "payment_from": chk["from"], "payment_from_matches": from_match, "payment_block": chk["block"], "verified_onchain": True}})
    except DuplicateKeyError:
        raise HTTPException(400, "This transaction has already been used for a payment")
    need(res.modified_count == 1, "This invoice is not waiting for payment")
    k = f"{FEE_KEY[inv['kind']]}.{inv['party']}"
    await db.transactions.update_one({"id": tx["id"]}, {"$set": {
        f"{k}.submitted_at": ts, f"{k}.confirmed_at": ts, f"{k}.tx_hash": h.lower(), f"{k}.verified": True}})
    await notify(tx, others(inv), f"{FEE_LABEL[inv['kind']]} verified — {inv['invoice_number']}",
                 f"{tx['reference']}: the {inv['party']} paid {eth(chk['value_eth'])} on-chain (block {chk['block']})"
                 + ("" if from_match else f" — note: sent from {chk['from']}, not the party's registered wallet") + ".")
    await log(tx, user, f"{FEE_LABEL[inv['kind']]} verified on-chain for {inv['invoice_number']}", f"{h} — {eth(chk['value_eth'])} from {chk['from']}")


@api.post("/invoices/{inv_id}/pay")
async def pay_invoice(inv_id: str, body: Optional[PayIn] = None, user: dict = Depends(current_user)):
    inv = await load_invoice(inv_id, user)
    need(user["id"] == inv["responsible_user_id"], "Only the billed party can pay this invoice")
    need(inv["status"] == "Unpaid", "This invoice is not waiting for payment")
    tx = await load_tx(inv["transaction_id"], user)
    need(not tx.get("on_hold"), "This deal is on hold")
    h = (body.tx_hash if body else "").strip()
    wallet = ""
    if inv["kind"] in FEE_KEY and inv.get("currency") == "ETH":
        wallet = await fee_wallet()
        need(bool(wallet), "The admin hasn't set the payment wallet yet")
        if h:
            await verify_invoice_payment(inv, tx, user, h, wallet)
            return await load_invoice(inv_id, user)
    ts = now()
    await db.invoices.update_one({"id": inv_id}, {"$set": {"status": "Payment Sent", "submitted_at": ts, "payment_to": wallet,
                                                         "payment_ref": "PAY-" + secrets.token_hex(4).upper()}})
    if inv["kind"] in FEE_KEY:
        await db.transactions.update_one({"id": tx["id"]}, {"$set": {f"{FEE_KEY[inv['kind']]}.{inv['party']}.submitted_at": ts}})
    await notify(tx, others(inv), f"Payment sent — {inv['invoice_number']}", f"{tx['reference']}: the {inv['party']} says they paid {amt(inv)}. Waiting for the admin to confirm it arrived.")
    await log(tx, user, f"Payment sent for {inv['invoice_number']}", amt(inv))
    return await load_invoice(inv_id, user)


@api.post("/invoices/{inv_id}/confirm")
async def confirm_invoice(inv_id: str, user: dict = Depends(admin_user)):
    inv = await load_invoice(inv_id, user)
    need(inv["status"] == "Payment Sent", "No payment is waiting for confirmation")
    tx = await load_tx(inv["transaction_id"], user)
    need(not tx.get("on_hold"), "This deal is on hold")
    ts = now()
    await db.invoices.update_one({"id": inv_id}, {"$set": {"status": "Paid", "paid_at": ts}})
    if inv["kind"] in FEE_KEY:
        await db.transactions.update_one({"id": tx["id"]}, {"$set": {f"{FEE_KEY[inv['kind']]}.{inv['party']}.confirmed_at": ts}})
    await notify(tx, [inv["party"]], f"Payment confirmed — {inv['invoice_number']}", f"{tx['reference']}: your payment was confirmed.")
    await log(tx, user, f"Payment confirmed for {inv['invoice_number']}")
    return await load_invoice(inv_id, user)


@api.get("/invoices/{inv_id}/pdf")
async def invoice_pdf(inv_id: str, user: dict = Depends(current_user)):
    inv = await load_invoice(inv_id, user)
    sections = [
        ("Invoice", [("Invoice number", inv["invoice_number"]), ("Deal reference", inv["reference"]),
                     ("Responsible party", f"{inv['responsible_name']} ({inv['party']})"), ("Payment status", inv["status"]),
                     ("Date issued", inv["issued_at"][:19].replace("T", " ")), ("Date paid", (inv["paid_at"] or "—")[:19].replace("T", " "))]),
        ("Services", [(line["description"], amt({**inv, "amount": line["amount"]})) for line in inv["items"]] + [("TOTAL", amt(inv))]),
    ]
    pdf = build_report("Invoice", inv["reference"], sections)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{inv["invoice_number"]}.pdf"'})


# ---------- reports ----------
def report_sections(kind: str, tx: dict) -> list:
    base = [("Deal reference", tx["reference"]), ("Asset", "ETH"),
            ("Network", tx["network"]), ("Sender", tx["sender_name"]), ("Recipient", tx["recipient_name"]),
            ("Deal value", money(tx["usd_value"])), ("ETH price", money(tx["eth_price"])),
            ("ETH amount", eth(tx["eth_quantity"]))]
    dep, st, an = tx["deposit"], tx["settlement"], tx["analysis"]
    dep_rows = [("From wallet", dep.get("from_address")), ("Escrow wallet", dep.get("to_address")),
                ("Transaction hash", dep.get("tx_hash")), ("Block number", dep.get("block_number")),
                ("Verified", "On-chain (public Ethereum data)" if dep.get("verified_onchain") else "Confirmed by admin" if dep.get("confirmed_at") else "Pending"),
                ("Time", dep.get("initiated_at"))]
    sf = tx.get("settlement_fees") or {}
    fee_rows = [(f"{p.capitalize()} 50% fee share", f"{eth(sf[p]['eth_amount'])} ({money(sf[p]['usd_amount'])}) — "
                 + ("verified on-chain" if sf[p].get("verified") else "paid" if sf[p].get("confirmed_at") else "pending")) for p in ("sender", "recipient") if p in sf]
    if kind == "agreement":
        a = tx["agreement"]
        return [("Deal", base), ("Signatures", [
            ("Agreement issued", a["issued_at"]), ("Signed by sender", a["sender_accepted_at"]), ("Signed by recipient", a["recipient_accepted_at"])])]
    if kind == "deposit":
        return [("Deal", base), ("Deposit", dep_rows)]
    if kind == "verification":
        return [("Deal", base[:5]), ("Checks", [(c["label"], f"{c['status']}{' — ' + c['note'] if c.get('note') else ''}") for c in tx["compliance"].values()]),
                ("Sender wallet screening", [("Risk score", f"{an.get('risk_score')}/100 — {an.get('risk_band')}" if an.get("risk_score") is not None else an.get("risk_band", "Not scanned")),
                                             ("Sanctions list match", "Yes" if an.get("sanctioned") else "No")]),
                ("Completed", [("Verified at", tx["aml"].get("completed_at"))])]
    return [("Deal", base), ("Deposit", dep_rows[:4]), ("Escrow fees (50/50)", fee_rows), ("Release", [
        ("Requested at", st.get("requested_at")), ("Released at", st.get("approved_at")),
        ("Release hash", st.get("release_tx_hash") or "Not provided"), ("Release block", st.get("release_block")),
        ("Recipient wallet", tx["onboarding"]["recipient"]["data"].get("wallet_address")), ("Status", "Completed")])]


@api.get("/reports/{tx_id}/{kind}/pdf")
async def report_pdf(tx_id: str, kind: str, user: dict = Depends(current_user)):
    tx = await load_tx(tx_id, user)
    meta = next((r for r in REPORT_TYPES if r[0] == kind), None)
    need(meta is not None, "Unknown document")
    need(step_flags(tx)[meta[2] - 1], "This document is not ready yet")
    await log(tx, user, f"Document downloaded: {meta[1]}")
    pdf = build_report(meta[1], tx["reference"], report_sections(kind, tx))
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{tx["reference"]}-{kind}.pdf"'})


@api.get("/reports/{tx_id}/uploads")
async def list_uploads(tx_id: str, category: str = "document", user: dict = Depends(current_user)):
    tx = await load_tx(tx_id, user)
    if category == "forensic" and user["role"] != "admin" and not tx["aml"].get("report_released_at"):
        return []
    cat = {"category": "forensic"} if category == "forensic" else {"category": {"$ne": "forensic"}}
    return await db.uploaded_reports.find({"transaction_id": tx_id, **cat}, {"_id": 0, "content": 0}).sort("uploaded_at", DESCENDING).to_list(200)


@api.post("/reports/{tx_id}/uploads")
async def upload_report(tx_id: str, title: str = Form(...), category: str = Form("document"), file: UploadFile = File(...), user: dict = Depends(admin_user)):
    tx = await load_tx(tx_id, user)
    content = await file.read()
    need(0 < len(content) <= 5 * 1024 * 1024, "File must be between 1 byte and 5 MB")
    doc = {"id": new_id(), "transaction_id": tx_id, "category": "forensic" if category == "forensic" else "document",
           "title": title.strip() or file.filename, "filename": file.filename,
           "content_type": file.content_type or "application/octet-stream", "size": len(content),
           "content": base64.b64encode(content).decode(), "uploaded_by": user["email"], "uploaded_at": now()}
    await db.uploaded_reports.insert_one(doc)
    if doc["category"] == "document" or tx["aml"].get("report_released_at"):
        where = "Forensics" if doc["category"] == "forensic" else "Documents"
        await notify(tx, ["sender", "recipient"], "New document shared", f"{tx['reference']}: the admin shared '{doc['title']}'. Open {where} to view it.")
    await log(tx, user, f"Document uploaded: {doc['title']}", file.filename)
    return {k: v for k, v in doc.items() if k not in ("_id", "content")}


@api.get("/reports/uploads/{up_id}/download")
async def download_upload(up_id: str, user: dict = Depends(current_user)):
    doc = await db.uploaded_reports.find_one({"id": up_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Not found")
    tx = await load_tx(doc["transaction_id"], user)
    if doc.get("category") == "forensic" and user["role"] != "admin" and not tx["aml"].get("report_released_at"):
        raise HTTPException(404, "Not found")
    return Response(base64.b64decode(doc["content"]), media_type=doc["content_type"],
                    headers={"Content-Disposition": f'attachment; filename="{doc["filename"]}"'})


# ---------- forensics (live on-chain data) ----------
class ScanIn(BaseModel):
    address: str
    label: str = ""


def scan_summary(s: dict) -> dict:
    r = s["report"]
    return {"id": s["id"], "address": r["address"], "label": s.get("label", ""), "balance_eth": r["balance_eth"],
            "risk": r["risk"], "sanctioned": r["sanctions"]["listed"], "created_at": s["created_at"], "created_by": s["created_by"]}


@api.post("/forensics/scan")
async def forensic_scan(body: ScanIn, user: dict = Depends(current_user)):
    addr = body.address.strip()
    need(forensics.valid(addr), "Enter a valid Ethereum address (0x followed by 40 hex characters)")
    try:
        report = await forensics.analyse(addr)
    except Exception as e:
        logger.error("forensic scan failed: %s", e)
        raise HTTPException(502, f"Could not read blockchain data: {e}")
    doc = {"id": new_id(), "label": body.label.strip(), "report": report, "created_at": now(), "created_by": user["email"], "user_id": user["id"]}
    await db.forensic_scans.insert_one(dict(doc))
    await log(None, user, "Forensic scan", f"{addr} — risk {report['risk']['band']} ({report['risk']['score']}/100)")
    return {**scan_summary(doc), "report": report}


def scan_scope(user: dict) -> dict:
    return {} if user["role"] == "admin" else {"user_id": user["id"]}


@api.get("/forensics/scans")
async def forensic_scans(user: dict = Depends(current_user)):
    docs = await db.forensic_scans.find(scan_scope(user), {"_id": 0}).sort("created_at", DESCENDING).to_list(100)
    return [scan_summary(d) for d in docs]


async def load_scan(scan_id: str, user: dict) -> dict:
    doc = await db.forensic_scans.find_one({"id": scan_id, **scan_scope(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Scan not found")
    return doc


@api.get("/forensics/scans/{scan_id}")
async def forensic_scan_get(scan_id: str, user: dict = Depends(current_user)):
    doc = await load_scan(scan_id, user)
    return {**scan_summary(doc), "report": doc["report"]}


@api.get("/forensics/scans/{scan_id}/pdf")
async def forensic_pdf(scan_id: str, user: dict = Depends(current_user)):
    doc = await load_scan(scan_id, user)
    r = doc["report"]
    a, s, rs = r["activity"], r["sanctions"], r["risky_services"]
    sections = [
        ("Subject wallet", [("Address", r["address"]), ("Label", doc.get("label") or "—"), ("Network", r["chain"]),
                            ("Account type", "Smart contract" if r["is_contract"] else "Externally owned account (EIP-7702 delegated)" if r.get("delegated_7702") else "Externally owned account"),
                            ("Current ETH balance", f"{r['balance_eth']:,.6f} ETH")]),
        ("Risk assessment", [("Risk score", f"{r['risk']['score']}/100"), ("Risk band", r["risk"]["band"])] + [("Finding", x) for x in r["risk"]["reasons"]]),
        ("Sanctions screening", [("Wallet on OFAC list", "YES" if s["listed"] else "No"), ("Sanctioned counterparties", len(s["counterparty_hits"])),
                                 ("Addresses screened against", f"{s['list_size']:,}"), ("List source", s["list_source"]), ("List retrieved", s["list_loaded_at"] or "unavailable")]),
        ("Mixer / high-risk service exposure", [("Wallet is a known service", rs["self"] or "No"), ("Exposed counterparties", len(rs["counterparty_hits"]))]
         + [(c["address"], c["service"]) for c in rs["counterparty_hits"]]),
        ("Transaction history", [("First activity", a["first_seen"] or "—"), ("Last activity", a["last_seen"] or "—"),
                                 ("Normal / internal / token transfers", f"{a['normal_tx']:,} / {a['internal_tx']:,} / {a['token_transfers']:,}"),
                                 ("Total ETH received", f"{a['eth_in']:,.6f} ETH ({a['tx_in']:,} tx)"), ("Total ETH sent", f"{a['eth_out']:,.6f} ETH ({a['tx_out']:,} tx)"),
                                 ("Failed transactions", a["failed_tx"]), ("Unique counterparties", a["unique_counterparties"]),
                                 ("Coverage", "Most recent records per category (provider limit reached)" if a["history_capped"] else "Full history")]),
        ("Top counterparties", [("Address", "Received ETH", "Sent ETH", "Interactions", "Flags")] + [
            (c["address"], f"{c['received_eth']:,.4f}", f"{c['sent_eth']:,.4f}", c["interactions"],
             ", ".join(x for x in ["OFAC" if c["sanctioned"] else "", c["service"] or ""] if x) or "—") for c in r["counterparties"][:15]]),
        ("Token holdings", [("Token", "Current balance", "Received", "Sent", "Transfers")] + [
            (f"{t['symbol']} ({t['contract'][:10]}…)", f"{t['balance']:,.4f}" if t.get("balance") is not None else "—", f"{t['received']:,.4f}", f"{t['sent']:,.4f}", t["transfers"]) for t in r["tokens"][:15]]),
        ("Recent transactions", [("Hash", "Time (UTC)", "Value ETH", "Status")] + [
            (t["hash"], t["time"][:19].replace("T", " "), f"{t['value_eth']:,.6f}", t["status"]) for t in r["recent_transactions"][:15]]),
        ("Method", [("Data source", r["data_source"]), ("Generated", r["generated_at"]), ("Requested by", doc["created_by"]),
                    ("Scope", "Direct (1-hop) counterparties of the subject wallet. Verify any hit independently before acting.")]),
    ]
    sub = f"Subject: <b>{r['address']}</b> &nbsp;|&nbsp; Generated {r['generated_at'][:19].replace('T', ' ')} UTC &nbsp;|&nbsp; Report ID {doc['id'][:8].upper()}"
    pdf = build_forensic_report("On-Chain Forensic Analysis — Wallet Due-Diligence Report", sub, sections)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="forensic-{r["address"][:10]}.pdf"'})


# ---------- notifications, audit, users ----------
@api.get("/notifications")
async def list_notifications(user: dict = Depends(current_user)):
    return await db.notifications.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", DESCENDING).to_list(100)


@api.post("/notifications/read-all")
async def read_all(user: dict = Depends(current_user)):
    await db.notifications.update_many({"user_id": user["id"]}, {"$set": {"read": True}})
    return {"ok": True}


@api.post("/notifications/{n_id}/read")
async def read_one(n_id: str, user: dict = Depends(current_user)):
    await db.notifications.update_one({"id": n_id, "user_id": user["id"]}, {"$set": {"read": True}})
    return {"ok": True}


@api.get("/audit")
async def audit(transaction_id: Optional[str] = None, user: dict = Depends(current_user)):
    q: Dict[str, Any] = {}
    if user["role"] != "admin":
        ids = [t["id"] async for t in db.transactions.find(tx_scope(user), {"id": 1})]
        q["transaction_id"] = {"$in": ids}
    if transaction_id:
        if user["role"] != "admin" and transaction_id not in q["transaction_id"]["$in"]:
            return []
        q["transaction_id"] = transaction_id
    return await db.audit_logs.find(q, {"_id": 0}).sort("timestamp", DESCENDING).to_list(1000)


@api.get("/users")
async def list_users(user: dict = Depends(admin_user)):
    return [public_user(u) async for u in db.users.find({}, {"_id": 0})]


# ---------- accounts: admin view & complete deletion ----------
PARTIES = ("sender", "recipient")


def slots(t: dict, u: dict) -> List[str]:
    inv = t.get("invite_emails") or {}
    return [p for p in PARTIES if t.get(f"{p}_user_id") == u["id"] or t.get(f"{p}_email") == u["email"] or inv.get(p) == u["email"]]


def deal_query(u: dict) -> dict:
    return {"$or": [c for p in PARTIES for c in ({f"{p}_user_id": u["id"]}, {f"{p}_email": u["email"]}, {f"invite_emails.{p}": u["email"]})]}


def in_escrow(t: dict) -> bool:
    return bool((t.get("deposit") or {}).get("initiated_at")) and not t.get("completed_at")


def deal_brief(t: dict) -> dict:
    return {"id": t["id"], "reference": t["reference"], "status": status_of(t), "in_escrow": in_escrow(t),
            "sender_name": t["sender_name"], "recipient_name": t["recipient_name"]}


def mentions(v: str, whole: bool = False) -> re.Pattern:
    return re.compile(f"^{re.escape(v)}$" if whole else re.escape(v), re.I)


async def deletion_scope(u: dict) -> dict:
    """Everything that belongs to or mentions this account: every deal they are on (for both parties) and all of
    its invoices, documents, messages, wallet scans and activity, plus anything else naming their email or wallet."""
    deals = await db.transactions.find(deal_query(u), {"_id": 0}).to_list(5000)
    ids = [t["id"] for t in deals]
    wallets = sorted({w.lower() for t in deals for p in slots(t, u)
                      if (w := str(((t.get("onboarding") or {}).get(p) or {}).get("data", {}).get("wallet_address", "")).strip())})
    text = [mentions(u["email"])] + [mentions(w) for w in wallets]
    filters = {
        "invoices": {"$or": [{"transaction_id": {"$in": ids}}, {"responsible_user_id": u["id"]}]},
        "uploaded_reports": {"transaction_id": {"$in": ids}},
        "notifications": {"$or": [{"transaction_id": {"$in": ids}}, {"user_id": u["id"]}]},
        "forensic_scans": {"$or": [{"transaction_id": {"$in": ids}}, {"user_id": u["id"]}, {"created_by": u["email"]},
                                   {"report.address": {"$in": [mentions(w, whole=True) for w in wallets]}}]},
        "audit_logs": {"$or": [{"transaction_id": {"$in": ids}}, {"actor": u["email"]}, {"action": {"$in": text}}, {"detail": {"$in": text}}]},
    }
    return {"deals": deals, "ids": ids, "filters": filters}


async def load_account(user_id: str, admin: dict) -> dict:
    u = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not u:
        raise HTTPException(404, "Account not found")
    need(u["id"] != admin["id"], "You can't delete your own account")
    need(u["role"] in PARTIES, "Administrator accounts can't be deleted")
    return u


@api.get("/accounts")
async def list_accounts(admin: dict = Depends(admin_user)):
    txs = await db.transactions.find({}, {"_id": 0}).sort("created_at", ASCENDING).to_list(5000)
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", ASCENDING).to_list(5000)
    return [{**public_user(u), "created_at": u.get("created_at"), "is_you": u["id"] == admin["id"],
             "deletable": u["role"] in PARTIES and u["id"] != admin["id"],
             "deals": [deal_brief(t) for t in txs if slots(t, u)]} for u in users]


@api.get("/accounts/{user_id}/deletion-preview")
async def deletion_preview(user_id: str, admin: dict = Depends(admin_user)):
    u = await load_account(user_id, admin)
    scope = await deletion_scope(u)
    counts = {"deals": len(scope["ids"])}
    for k, q in scope["filters"].items():
        counts[k] = await db[k].count_documents(q)
    return {"account": public_user(u), "deals": [deal_brief(t) for t in scope["deals"]],
            "blocked": [deal_brief(t) for t in scope["deals"] if in_escrow(t)], "counts": counts}


@api.delete("/accounts/{user_id}")
async def delete_account(user_id: str, admin: dict = Depends(admin_user)):
    u = await load_account(user_id, admin)
    scope = await deletion_scope(u)
    held = [t["reference"] for t in scope["deals"] if in_escrow(t)]
    need(not held, f"ETH is held in escrow on {', '.join(held)} — release the funds before deleting this account")
    await db.users.delete_one({"id": u["id"]})  # signs them out everywhere straight away
    counts = {"deals": (await db.transactions.delete_many({"id": {"$in": scope["ids"]}})).deleted_count}
    for k, q in scope["filters"].items():
        counts[k] = (await db[k].delete_many(q)).deleted_count
    n = counts["deals"]
    await log(None, admin, "Account deleted", f"A {u['role']} account was deleted" + (f", with {n} deal{'' if n == 1 else 's'}" if n else ""))
    return {"deleted": True, "counts": counts}


# ---------- seed ----------
DEMO_USERS = [
    {"email": "admin@vaultbridge.demo", "password": "AdminDemo#2026", "role": "admin", "name": "Alex Morgan", "organisation": BRAND},
    {"email": "sender@vaultbridge.demo", "password": "SenderDemo#2026", "role": "sender", "name": "Jordan Hale", "organisation": "Demo Investment Entity"},
    {"email": "recipient@vaultbridge.demo", "password": "RecipientDemo#2026", "role": "recipient", "name": "Riley Chen", "organisation": "Demo Acquisition Company"},
]


async def seed_users(first_run: bool):
    # Admin accounts are always kept up to date; the sample sender/recipient are created on the very first start only,
    # so an account the admin deletes never comes back after a restart.
    users = [u for u in DEMO_USERS if u["role"] == "admin" or first_run]
    if os.environ.get("OWNER_EMAIL") and os.environ.get("OWNER_PASSWORD"):
        users.append({"email": os.environ["OWNER_EMAIL"].lower(), "password": os.environ["OWNER_PASSWORD"], "role": "admin",
                      "name": "Platform Owner", "organisation": BRAND})
    for u in users:
        existing = await db.users.find_one({"email": u["email"]})
        fields = {"role": u["role"], "name": u["name"], "organisation": u["organisation"]}
        if existing:
            if not bcrypt.checkpw(u["password"].encode(), existing["password_hash"].encode()):
                fields["password_hash"] = hash_pw(u["password"])
            await db.users.update_one({"email": u["email"]}, {"$set": fields})
        else:
            await db.users.insert_one({"id": new_id(), "email": u["email"], "password_hash": hash_pw(u["password"]), **fields, "created_at": now()})


async def seed_data(first_run: bool):
    if not await db.settings.find_one({"key": "fees"}):
        await db.settings.insert_one({"key": "fees", "items": [{"code": c, "label": l, "amount": a, "party": p} for c, l, a, p in FEE_CATALOG]})
    if first_run and await db.transactions.count_documents({}) == 0:
        tx = await new_transaction("TSX-ETH-2026-001", 6_000_000_000.0, "Demo Investment Entity", "Demo Acquisition Company", "Ethereum Mainnet")
        await log(tx, None, "Deal created", "TSX-ETH-2026-001 created — waiting for the admin to send invitation emails")


app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


async def ensure_indexes():
    for collection, models in INDEXES.items():
        for model in models:
            try:
                await db[collection].create_indexes([model])
            except Exception as exc:
                logger.error("ensure_indexes(%s.%s): %s", collection, model.document["name"], exc)


@app.on_event("startup")
async def startup():
    first_run = not await db.settings.find_one({"key": "seeded"})
    await seed_users(first_run)
    await seed_data(first_run)
    if first_run:
        await db.settings.update_one({"key": "seeded"}, {"$set": {"at": now()}}, upsert=True)
    refresh_price_soon()  # make sure a recent ETH price is saved straight after a restart
    app.state.index_task = asyncio.create_task(ensure_indexes())


@app.on_event("shutdown")
async def shutdown():
    app.state.index_task.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.index_task
    client.close()
