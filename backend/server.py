import asyncio
import base64
import logging
import os
import random
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
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

try:
    from backend.pdf_reports import build_report, build_forensic_report
    from backend import forensics
except ModuleNotFoundError:
    from pdf_reports import build_report, build_forensic_report
    import forensics

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
JWT_SECRET = os.environ["JWT_SECRET"]
logger = logging.getLogger(__name__)

INDEXES = {
    "users": [IndexModel([("email", ASCENDING)], name="email", unique=True), IndexModel([("id", ASCENDING)], name="id", unique=True)],
    "transactions": [IndexModel([("id", ASCENDING)], name="id", unique=True), IndexModel([("reference", ASCENDING)], name="reference", unique=True)],
    "invoices": [IndexModel([("id", ASCENDING)], name="id", unique=True), IndexModel([("transaction_id", ASCENDING)], name="tx")],
    "audit_logs": [IndexModel([("transaction_id", ASCENDING)], name="tx"), IndexModel([("timestamp", DESCENDING)], name="ts")],
    "notifications": [IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_ts")],
    "uploaded_reports": [IndexModel([("id", ASCENDING)], name="id", unique=True), IndexModel([("transaction_id", ASCENDING)], name="tx")],
}

ETH_PRICE = 2350.0
REQUIRED_CONF = 12
CONF_INTERVAL = 2.0

FEE_CATALOG = [
    ("sender_onboarding", "Sender onboarding fee", 25000, "sender"),
    ("recipient_onboarding", "Recipient onboarding fee", 25000, "recipient"),
    ("escrow_admin", "Escrow administration", 1500000, "recipient"),
    ("blockchain_analytics", "Blockchain analytics", 75000, "recipient"),
    ("compliance", "Compliance assessment", 150000, "recipient"),
    ("custody_admin", "Custody administration", 600000, "recipient"),
    ("settlement_admin", "Settlement administration", 300000, "recipient"),
]
ENGAGEMENT_ITEMS = ["recipient_onboarding", "escrow_admin", "blockchain_analytics", "compliance", "custody_admin", "settlement_admin"]

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
    ("Admin approves both parties", "admin"),
    ("Both parties sign the agreement", "both"),
    ("Recipient pays the escrow fee", "recipient"),
    ("Admin confirms the fee payment", "admin"),
    ("Sender deposits ETH into escrow", "sender"),
    ("Admin verifies the deposit", "admin"),
    ("Sender requests release of funds", "sender"),
    ("Admin releases funds to recipient", "admin"),
]
STATUS_BY_STEP = {
    1: "Awaiting onboarding", 2: "Awaiting onboarding", 3: "Awaiting approval", 4: "Awaiting signatures",
    5: "Awaiting fee payment", 6: "Confirming fee payment", 7: "Awaiting deposit", 8: "Verifying deposit",
    9: "Funds held in escrow", 10: "Release pending",
}
REPORT_TYPES = [
    ("agreement", "Escrow agreement", 4),
    ("deposit", "Deposit receipt", 8),
    ("verification", "Verification report", 8),
    ("final", "Final settlement statement", 10),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def sim_address() -> str:
    return "0x" + secrets.token_hex(20)


def sim_hash() -> str:
    return "0x" + secrets.token_hex(32)


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
             "title": title, "body": body, "read": False, "created_at": now()} for i in ids]
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
    ob, ag = tx["onboarding"], tx["agreement"]
    dep, st, pay = tx["deposit"], tx["settlement"], tx["payment"]
    return [
        joined(ob["sender"]),
        joined(ob["recipient"]),
        all(ob[p]["status"] == "approved" for p in ("sender", "recipient")),
        bool(ag.get("sender_accepted_at") and ag.get("recipient_accepted_at")),
        bool(pay.get("submitted_at")),
        bool(pay.get("confirmed_at")),
        bool(dep.get("initiated_at")),
        bool(tx["aml"].get("completed_at")),
        bool(st.get("requested_at")),
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
    if step == 8 and tx["deposit"].get("confirmations", 0) < REQUIRED_CONF:
        return "Deposit confirming"
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
    dep = tx["deposit"]
    if dep.get("initiated_at") and dep.get("confirmations", 0) < REQUIRED_CONF:
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(dep["initiated_at"])).total_seconds()
        conf = min(REQUIRED_CONF, int(elapsed // CONF_INTERVAL))
        if conf != dep.get("confirmations", 0):
            dep["confirmations"] = conf
            res = await db.transactions.update_one(
                {"id": tx["id"], "deposit.confirmations": {"$lt": conf}}, {"$set": {"deposit.confirmations": conf}})
            if conf >= REQUIRED_CONF and res.modified_count:
                dep["confirmed_at"] = now()
                await db.transactions.update_one({"id": tx["id"]}, {"$set": {"deposit.confirmed_at": dep["confirmed_at"]}})
                await log(tx, None, "Deposit confirmed", f"{REQUIRED_CONF}/{REQUIRED_CONF} confirmations reached")
                await notify(tx, ["sender", "recipient", "admin"], "Deposit confirmed",
                             f"{tx['reference']}: the ETH deposit reached {REQUIRED_CONF} confirmations.")
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


async def new_transaction(reference: str, usd_value: float, sender_name: str, recipient_name: str, network: str) -> dict:
    sender = await db.users.find_one({"role": "sender"}, {"_id": 0})
    recipient = await db.users.find_one({"role": "recipient"}, {"_id": 0})
    qty = round(usd_value / ETH_PRICE, 6)
    party = {"status": "pending", "responded_at": None}
    ob = {"status": "not_started", "data": {}, "submitted_at": None, "reviewed_at": None, "note": ""}
    tx = {
        "id": new_id(), "reference": reference, "asset": "ETH", "usd_value": usd_value, "eth_price": ETH_PRICE,
        "eth_quantity": qty, "network": network, "sender_name": sender_name, "recipient_name": recipient_name,
        "sender_user_id": sender["id"], "recipient_user_id": recipient["id"],
        "sender_email": sender["email"], "recipient_email": recipient["email"],
        "escrow_vault_address": sim_address(), "sender_wallet_balance": round(qty + 125.5, 6),
        "recipient_wallet_balance": 0.0, "created_at": now(), "invitations_sent_at": now(),
        "invitations": {"sender": dict(party), "recipient": dict(party)},
        "onboarding": {"sender": dict(ob), "recipient": dict(ob)},
        "agreement": {"issued_at": None, "sender_accepted_at": None, "recipient_accepted_at": None},
        "payment": {"invoice_id": None, "submitted_at": None, "confirmed_at": None},
        "deposit": {"initiated_at": None, "confirmations": 0},
        "analysis": {}, "aml": {"completed_at": None},
        "compliance": {k: {"label": label, "status": "Pending", "note": "", "updated_at": now()} for k, label in COMPLIANCE_CHECKS},
        "report_access": {"sender": None, "recipient": None},
        "settlement": {"status": "none"}, "on_hold": False, "completed_at": None,
    }
    await db.transactions.insert_one(dict(tx))
    for p in ("sender", "recipient"):
        await notify(tx, [p], f"You're invited to escrow deal {reference}",
                     f"VaultBridge Escrow invites {tx[f'{p}_name']} to join deal {reference} as {p}. Value {money(usd_value)}. Open Home to join.", "email")
    return tx


# ---------- transactions ----------
class TxCreate(BaseModel):
    usd_value: float
    sender_name: str
    recipient_name: str
    network: str = "Ethereum Mainnet"


@api.get("/transactions")
async def list_transactions(user: dict = Depends(current_user)):
    txs = await db.transactions.find(tx_scope(user), {"_id": 0}).sort("created_at", ASCENDING).to_list(200)
    return [present(await refresh_deposit(t)) for t in txs]


@api.post("/transactions")
async def create_transaction(body: TxCreate, user: dict = Depends(admin_user)):
    if body.usd_value <= 0 or not body.sender_name.strip() or not body.recipient_name.strip():
        raise HTTPException(400, "Value and party names are required")
    n = await db.transactions.count_documents({}) + 1
    ref = f"VB-ETH-2026-{n:03d}"
    while await db.transactions.find_one({"reference": ref}):
        n += 1
        ref = f"VB-ETH-2026-{n:03d}"
    tx = await new_transaction(ref, body.usd_value, body.sender_name.strip(), body.recipient_name.strip(), body.network)
    await log(tx, user, "Deal created", f"{ref} — deal value {money(body.usd_value)}")
    return present(tx)


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
        need(tx["invitations"][party]["status"] != "declined", "You declined this invitation")
        need(tx["onboarding"][party]["status"] in ("not_started", "rejected"), "You have already joined this deal")
        required = ["legal_name", "contact_name", "contact_email", "wallet_address"]
        need(all(str(d.get(k, "")).strip() for k in required), "Please fill in all fields")
        w = str(d["wallet_address"]).strip()
        need(w.startswith("0x") and len(w) == 42, "Wallet address must start with 0x and be 42 characters long")
        data = {k: str(d.get(k, "")).strip() for k in required}
        sets[f"invitations.{party}"] = {"status": "accepted", "responded_at": now()}
        sets[f"onboarding.{party}"] = {"status": "submitted", "data": data, "submitted_at": now(), "reviewed_at": None, "note": ""}
        await notify(tx, ["admin"], f"{party.capitalize()} joined the deal", f"{tx['reference']}: {data['legal_name']} joined as {party} and is waiting for approval.")
        msg = f"{party.capitalize()} joined the deal"
    elif action == "decline":
        need(party is not None, "Only an invited party can decline")
        need(tx["invitations"][party]["status"] == "pending", "Invitation already answered")
        sets[f"invitations.{party}"] = {"status": "declined", "responded_at": now()}
        await notify(tx, ["admin"], f"Invitation declined by {party}", f"{tx['reference']}: the {party} declined the invitation.")
        msg = f"{party.capitalize()} declined the invitation"
    elif action == "approve_parties":
        need(is_admin, "Administrator only")
        need(step == 3, "Both parties must join first")
        for p in ("sender", "recipient"):
            sets[f"onboarding.{p}.status"] = "approved"
            sets[f"onboarding.{p}.reviewed_at"] = now()
        sets["agreement.issued_at"] = now()
        await notify(tx, ["sender", "recipient"], "You're approved — please sign the agreement", f"{tx['reference']}: both parties are approved. Open Home to sign the escrow agreement.")
        msg = "Both parties approved; agreement sent for signing"
    elif action == "reject_party":
        need(is_admin, "Administrator only")
        p = d.get("party")
        need(p in ("sender", "recipient") and tx["onboarding"][p]["status"] == "submitted", "That party is not waiting for approval")
        sets[f"onboarding.{p}.status"] = "rejected"
        sets[f"onboarding.{p}.note"] = str(d.get("note", ""))
        await notify(tx, [p], "Please update your details", f"{tx['reference']}: the admin asked you to update your details. {d.get('note', '')}")
        msg = f"Asked {p} to update their details"
    elif action == "sign_agreement":
        need(party is not None, "Only a party can sign the agreement")
        need(step == 4, "The agreement is not ready to sign")
        need(not tx["agreement"].get(f"{party}_accepted_at"), "You already signed")
        sets[f"agreement.{party}_accepted_at"] = now()
        other = "recipient" if party == "sender" else "sender"
        if tx["agreement"].get(f"{other}_accepted_at"):
            fees = (await db.settings.find_one({"key": "fees"}))["items"]
            inv = await make_invoice(tx, "recipient", [f for f in fees if f["code"] in ENGAGEMENT_ITEMS], "engagement")
            sets["payment.invoice_id"] = inv["id"]
        await notify(tx, ["admin"], f"Agreement signed by {party}", f"{tx['reference']}: {party} signed the escrow agreement.")
        msg = f"{party.capitalize()} signed the agreement"
    elif action == "deposit":
        need(party == "sender", "Only the sender can deposit")
        need(step == 7, "Deposit is not open yet")
        sets["deposit"] = {
            "initiated_at": now(), "confirmations": 0, "required": REQUIRED_CONF,
            "from_address": tx["onboarding"]["sender"]["data"]["wallet_address"], "to_address": tx["escrow_vault_address"],
            "eth_quantity": tx["eth_quantity"], "tx_hash": sim_hash(), "block_number": random.randint(21_400_000, 21_900_000),
            "network_fee_eth": round(random.uniform(0.0021, 0.0068), 6), "gas_used": random.randint(21000, 64000),
        }
        sets["sender_wallet_balance"] = round(tx["sender_wallet_balance"] - tx["eth_quantity"], 6)
        await notify(tx, ["recipient", "admin"], "ETH deposit sent", f"{tx['reference']}: the sender deposited {eth(tx['eth_quantity'])} into escrow.")
        msg = f"Deposit of {eth(tx['eth_quantity'])} sent to escrow"
    elif action == "verify_deposit":
        need(is_admin, "Administrator only")
        need(step == 8, "There is no deposit to verify yet")
        need(tx["deposit"].get("confirmations", 0) >= REQUIRED_CONF, "Wait until the deposit reaches 12 confirmations")
        need(not any(c["status"] in ("Rejected", "More Info Needed") for c in tx["compliance"].values()), "Resolve checks marked Rejected or More Info Needed first")
        sets["analysis"] = {
            "generated_at": now(), "risk_score": random.randint(8, 22), "risk_band": "Low",
            "hops_analysed": 5, "counterparties_traced": random.randint(14, 40),
            "exposure": [{"category": "Exchanges", "percent": 62.4}, {"category": "OTC desks", "percent": 21.3},
                         {"category": "Custodians", "percent": 14.1}, {"category": "Unattributed", "percent": 2.2},
                         {"category": "High-risk", "percent": 0.0}],
        }
        for k, c in tx["compliance"].items():
            sets[f"compliance.{k}"] = {**c, "status": "Approved", "updated_at": now()}
        sets["aml.completed_at"] = now()
        await notify(tx, ["sender", "recipient"], "Deposit verified", f"{tx['reference']}: the deposit passed all checks and is held in escrow.")
        msg = "Deposit verified — all checks approved"
    elif action == "set_compliance":
        need(is_admin, "Administrator only")
        k, s = d.get("check"), d.get("status")
        need(k in tx["compliance"] and s in COMPLIANCE_STATUSES, "Invalid check update")
        need(not tx["aml"].get("completed_at"), "Checks are already completed")
        sets[f"compliance.{k}"] = {"label": tx["compliance"][k]["label"], "status": s, "note": str(d.get("note", "")), "updated_at": now()}
        msg = f"{tx['compliance'][k]['label']} set to {s}"
    elif action == "request_release":
        need(party == "sender", "Only the sender can request release")
        need(step == 9, "Release cannot be requested yet")
        sets["settlement"] = {"status": "requested", "requested_at": now(), "requested_by": user["email"], "release_eth": tx["eth_quantity"]}
        await notify(tx, ["recipient", "admin"], "Release requested", f"{tx['reference']}: the sender asked to release {eth(tx['eth_quantity'])} to the recipient.")
        msg = "Sender requested release of funds"
    elif action == "release":
        need(is_admin, "Administrator only")
        need(step == 10, "No release request is waiting")
        if d.get("decision") == "approved":
            ts = now()
            sets.update({"settlement.status": "released", "settlement.approved_at": ts, "settlement.credited_at": ts,
                         "settlement.release_tx_hash": sim_hash(), "settlement.release_block": random.randint(21_900_001, 22_100_000),
                         "recipient_wallet_balance": round(tx["recipient_wallet_balance"] + tx["eth_quantity"], 6), "completed_at": ts})
            await notify(tx, ["sender", "recipient"], "Funds released — deal completed", f"{tx['reference']}: {eth(tx['eth_quantity'])} was released to the recipient.")
            msg = "Funds released to recipient — deal completed"
        else:
            sets["settlement"] = {"status": "rejected", "rejected_at": now(), "note": str(d.get("note", ""))}
            await notify(tx, ["sender", "recipient"], "Release request declined", f"{tx['reference']}: the release request was declined. {d.get('note', '')}")
            msg = "Release request declined"
    elif action in ("hold", "resume"):
        need(is_admin, "Administrator only")
        sets["on_hold"] = action == "hold"
        msg = "Deal placed on hold" if action == "hold" else "Deal resumed"
    else:
        raise HTTPException(400, "Unknown action")

    await db.transactions.update_one({"id": tx_id}, {"$set": sets})
    await log(tx, user, msg, str(d.get("note", "")) if d.get("note") else "")
    return present(await load_tx(tx_id, user))


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


async def make_invoice(tx: dict, party: str, fee_items: List[dict], kind: str, user: Optional[dict] = None) -> dict:
    n = await next_counter("invoice")
    lines = [{"code": f["code"], "description": f["label"], "amount": f["amount"]} for f in fee_items]
    inv = {
        "id": new_id(), "invoice_number": f"VB-INV-2026-{n:04d}", "transaction_id": tx["id"], "reference": tx["reference"],
        "kind": kind, "party": party,
        "responsible_name": tx[f"{party}_name"], "responsible_user_id": tx[f"{party}_user_id"],
        "items": lines, "amount": sum(line["amount"] for line in lines), "currency": "USD",
        "status": "Unpaid", "issued_at": now(), "submitted_at": None, "paid_at": None,
    }
    await db.invoices.insert_one(dict(inv))
    await notify(tx, [party], f"New invoice {inv['invoice_number']}", f"{tx['reference']}: an invoice for {money(inv['amount'])} is ready. Open Payments to pay it.")
    await log(tx, user, f"Invoice {inv['invoice_number']} issued", f"{'Escrow fee' if kind == 'engagement' else 'Invoice'} to {party} — {money(inv['amount'])}")
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


@api.post("/invoices/{inv_id}/pay")
async def pay_invoice(inv_id: str, user: dict = Depends(current_user)):
    inv = await load_invoice(inv_id, user)
    need(user["id"] == inv["responsible_user_id"], "Only the billed party can pay this invoice")
    need(inv["status"] == "Unpaid", "This invoice is not waiting for payment")
    tx = await load_tx(inv["transaction_id"], user)
    need(not tx.get("on_hold"), "This deal is on hold")
    ts = now()
    await db.invoices.update_one({"id": inv_id}, {"$set": {"status": "Payment Sent", "submitted_at": ts, "payment_ref": "PAY-" + secrets.token_hex(4).upper()}})
    if inv["kind"] == "engagement":
        await db.transactions.update_one({"id": tx["id"]}, {"$set": {"payment.submitted_at": ts}})
    await notify(tx, ["admin"], f"Payment sent — {inv['invoice_number']}", f"{tx['reference']}: {inv['party']} paid {money(inv['amount'])}. Please confirm.")
    await log(tx, user, f"Payment sent for {inv['invoice_number']}", money(inv["amount"]))
    return await load_invoice(inv_id, user)


@api.post("/invoices/{inv_id}/confirm")
async def confirm_invoice(inv_id: str, user: dict = Depends(admin_user)):
    inv = await load_invoice(inv_id, user)
    need(inv["status"] == "Payment Sent", "No payment is waiting for confirmation")
    tx = await load_tx(inv["transaction_id"], user)
    need(not tx.get("on_hold"), "This deal is on hold")
    ts = now()
    await db.invoices.update_one({"id": inv_id}, {"$set": {"status": "Paid", "paid_at": ts}})
    if inv["kind"] == "engagement":
        await db.transactions.update_one({"id": tx["id"]}, {"$set": {"payment.confirmed_at": ts}})
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
        ("Services", [(line["description"], money(line["amount"])) for line in inv["items"]] + [("TOTAL", money(inv["amount"]))]),
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
                ("Confirmations", f"{dep.get('confirmations')}/{REQUIRED_CONF}"), ("Network fee", eth(dep.get("network_fee_eth", 0))),
                ("Time", dep.get("initiated_at"))]
    if kind == "agreement":
        a = tx["agreement"]
        return [("Deal", base), ("Signatures", [
            ("Agreement issued", a["issued_at"]), ("Signed by sender", a["sender_accepted_at"]), ("Signed by recipient", a["recipient_accepted_at"])])]
    if kind == "deposit":
        return [("Deal", base), ("Deposit", dep_rows)]
    if kind == "verification":
        return [("Deal", base[:5]), ("Checks", [(c["label"], f"{c['status']}{' — ' + c['note'] if c.get('note') else ''}") for c in tx["compliance"].values()]),
                ("Wallet analysis", [("Risk score", f"{an.get('risk_score')}/100 — {an.get('risk_band')}"), ("Hops analysed", an.get("hops_analysed")),
                                     ("Counterparties traced", an.get("counterparties_traced"))] + [(e["category"], f"{e['percent']}%") for e in an.get("exposure", [])]),
                ("Completed", [("Verified at", tx["aml"].get("completed_at"))])]
    return [("Deal", base), ("Deposit", dep_rows[:4]), ("Release", [
        ("Requested at", st.get("requested_at")), ("Released at", st.get("approved_at")),
        ("Release hash", st.get("release_tx_hash")), ("Release block", st.get("release_block")),
        ("Recipient balance", eth(tx["recipient_wallet_balance"])), ("Status", "Completed")])]


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
async def list_uploads(tx_id: str, user: dict = Depends(current_user)):
    await load_tx(tx_id, user)
    return await db.uploaded_reports.find({"transaction_id": tx_id}, {"_id": 0, "content": 0}).sort("uploaded_at", DESCENDING).to_list(200)


@api.post("/reports/{tx_id}/uploads")
async def upload_report(tx_id: str, title: str = Form(...), file: UploadFile = File(...), user: dict = Depends(admin_user)):
    tx = await load_tx(tx_id, user)
    content = await file.read()
    need(0 < len(content) <= 5 * 1024 * 1024, "File must be between 1 byte and 5 MB")
    doc = {"id": new_id(), "transaction_id": tx_id, "title": title.strip() or file.filename, "filename": file.filename,
           "content_type": file.content_type or "application/octet-stream", "size": len(content),
           "content": base64.b64encode(content).decode(), "uploaded_by": user["email"], "uploaded_at": now()}
    await db.uploaded_reports.insert_one(doc)
    await notify(tx, ["sender", "recipient"], "New document shared", f"{tx['reference']}: the admin shared '{doc['title']}'.")
    await log(tx, user, f"Document uploaded: {doc['title']}", file.filename)
    return {k: v for k, v in doc.items() if k not in ("_id", "content")}


@api.get("/reports/uploads/{up_id}/download")
async def download_upload(up_id: str, user: dict = Depends(current_user)):
    doc = await db.uploaded_reports.find_one({"id": up_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Not found")
    await load_tx(doc["transaction_id"], user)
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
        ("Token activity", [("Token", "Received", "Sent", "Net", "Transfers")] + [
            (f"{t['symbol']} ({t['contract'][:10]}…)", f"{t['received']:,.4f}", f"{t['sent']:,.4f}", f"{t['net']:,.4f}", t["transfers"]) for t in r["tokens"][:15]]),
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


@api.post("/admin/reset")
async def reset_demo(user: dict = Depends(admin_user)):
    for c in ("transactions", "invoices", "audit_logs", "notifications", "uploaded_reports", "counters", "settings"):
        await db[c].delete_many({})
    await seed_data()
    await log(None, user, "Demo reset", "All records restored to the starting state")
    return {"ok": True}


# ---------- seed ----------
DEMO_USERS = [
    {"email": "admin@vaultbridge.demo", "password": "AdminDemo#2026", "role": "admin", "name": "Alex Morgan", "organisation": "VaultBridge Escrow"},
    {"email": "sender@vaultbridge.demo", "password": "SenderDemo#2026", "role": "sender", "name": "Jordan Hale", "organisation": "Demo Investment Entity"},
    {"email": "recipient@vaultbridge.demo", "password": "RecipientDemo#2026", "role": "recipient", "name": "Riley Chen", "organisation": "Demo Acquisition Company"},
]


async def seed_users():
    users = list(DEMO_USERS)
    if os.environ.get("OWNER_EMAIL") and os.environ.get("OWNER_PASSWORD"):
        users.append({"email": os.environ["OWNER_EMAIL"].lower(), "password": os.environ["OWNER_PASSWORD"], "role": "admin",
                      "name": "Platform Owner", "organisation": "VaultBridge Escrow"})
    for u in users:
        existing = await db.users.find_one({"email": u["email"]})
        fields = {"role": u["role"], "name": u["name"], "organisation": u["organisation"]}
        if existing:
            if not bcrypt.checkpw(u["password"].encode(), existing["password_hash"].encode()):
                fields["password_hash"] = hash_pw(u["password"])
            await db.users.update_one({"email": u["email"]}, {"$set": fields})
        else:
            await db.users.insert_one({"id": new_id(), "email": u["email"], "password_hash": hash_pw(u["password"]), **fields, "created_at": now()})


async def seed_data():
    if not await db.settings.find_one({"key": "fees"}):
        await db.settings.insert_one({"key": "fees", "items": [{"code": c, "label": l, "amount": a, "party": p} for c, l, a, p in FEE_CATALOG]})
    if await db.transactions.count_documents({}) == 0:
        tx = await new_transaction("VB-ETH-2026-001", 6_000_000_000.0, "Demo Investment Entity", "Demo Acquisition Company", "Ethereum Mainnet")
        await log(tx, None, "Deal created", "VB-ETH-2026-001 created and invitations sent")


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
    await seed_users()
    await seed_data()
    app.state.index_task = asyncio.create_task(ensure_indexes())


@app.on_event("shutdown")
async def shutdown():
    app.state.index_task.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.index_task
    client.close()
