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
    from backend.pdf_reports import build_report
except ModuleNotFoundError:
    from pdf_reports import build_report

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
JWT_SECRET = os.environ["JWT_SECRET"]
logger = logging.getLogger(__name__)

INDEXES = {
    "users": [IndexModel([("email", ASCENDING)], name="email", unique=True), IndexModel([("id", ASCENDING)], name="id", unique=True)],
    "transactions": [IndexModel([("id", ASCENDING)], name="id", unique=True)],
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
COMPLIANCE_STATUSES = ["Pending", "Under Review", "Additional Information Required", "Simulated Approval", "Simulated Rejection"]

STEPS = [
    ("Administrator creates transaction", "admin"),
    ("Invitations sent to both parties", "admin"),
    ("Sender accepts invitation", "sender"),
    ("Recipient accepts invitation", "recipient"),
    ("Both parties submit onboarding", "both"),
    ("Onboarding approved & agreement issued for review", "admin"),
    ("Both parties accept escrow agreement", "both"),
    ("Engagement invoice issued to recipient", "admin"),
    ("Recipient makes simulated payment", "recipient"),
    ("Administrator confirms simulated payment", "admin"),
    ("Sender initiates simulated ETH deposit", "sender"),
    ("Simulated network confirmations (12/12)", "network"),
    ("Simulated blockchain analysis generated", "admin"),
    ("Simulated AML review completed", "admin"),
    ("Both parties access verification reports", "both"),
    ("Settlement request initiated & acknowledged", "both"),
    ("Administrator approves simulated release", "admin"),
    ("Recipient receives simulated ETH balance", "recipient"),
    ("Transaction marked COMPLETED — SIMULATION", "admin"),
]
STATUS_BY_STEP = {
    2: "Awaiting onboarding", 3: "Awaiting invitation acceptance", 4: "Awaiting invitation acceptance",
    5: "Onboarding in progress", 6: "Onboarding under review", 7: "Agreement under review",
    8: "Awaiting engagement invoice", 9: "Awaiting engagement payment", 10: "Payment confirmation pending",
    11: "Awaiting simulated deposit", 12: "Confirming on simulated network", 13: "Blockchain analysis pending",
    14: "AML review in progress", 15: "Verification reports available", 16: "Settlement request pending",
    17: "Awaiting release approval", 18: "Release executed — awaiting receipt", 19: "Finalisation pending",
}
REPORT_TYPES = [
    ("engagement", "Escrow engagement confirmation", 7),
    ("deposit", "Simulated ETH deposit confirmation", 12),
    ("blockchain_analysis", "Simulated blockchain analysis", 13),
    ("compliance", "Simulated compliance report", 14),
    ("custody", "Simulated custody statement", 12),
    ("settlement", "Simulated settlement statement", 17),
    ("final", "Final transaction completion report", 19),
]
VERIFICATION_REPORTS = {"blockchain_analysis", "compliance"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def sim_address() -> str:
    return "0x" + secrets.token_hex(20)


def sim_hash() -> str:
    return "0x" + secrets.token_hex(32)


def money(v: float) -> str:
    return f"${v:,.2f} (fictional)"


def eth(v: float) -> str:
    return f"{v:,.6f} ETH (simulated)"


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


def step_flags(tx: dict) -> List[bool]:
    inv, ob, ag = tx["invitations"], tx["onboarding"], tx["agreement"]
    dep, st, pay = tx["deposit"], tx["settlement"], tx["payment"]
    return [
        True,
        bool(tx.get("invitations_sent_at")),
        inv["sender"]["status"] == "accepted",
        inv["recipient"]["status"] == "accepted",
        all(ob[p]["status"] in ("submitted", "approved") for p in ("sender", "recipient")),
        bool(ag.get("issued_at")),
        bool(ag.get("sender_accepted_at") and ag.get("recipient_accepted_at")),
        bool(pay.get("invoice_id")),
        bool(pay.get("submitted_at")),
        bool(pay.get("confirmed_at")),
        bool(dep.get("initiated_at")),
        dep.get("confirmations", 0) >= REQUIRED_CONF,
        bool(tx["analysis"].get("generated_at")),
        bool(tx["aml"].get("completed_at")),
        bool(tx["report_access"].get("sender") and tx["report_access"].get("recipient")),
        bool(st.get("requested_at") and st.get("recipient_acknowledged_at")),
        bool(st.get("approved_at")),
        bool(st.get("credited_at")),
        bool(tx.get("completed_at")),
    ]


def current_step(tx: dict) -> int:
    for i, done in enumerate(step_flags(tx)):
        if not done:
            return i + 1
    return 20


def status_of(tx: dict) -> str:
    if tx.get("completed_at"):
        return "COMPLETED — SIMULATION"
    if tx.get("on_hold"):
        return "ON HOLD"
    if any(tx["invitations"][p]["status"] == "declined" for p in ("sender", "recipient")):
        return "Invitation declined"
    return STATUS_BY_STEP.get(current_step(tx), "In progress")


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
                await log(tx, None, "Simulated deposit confirmed", f"{REQUIRED_CONF}/{REQUIRED_CONF} simulated confirmations reached")
                await notify(tx, ["sender", "recipient", "admin"], "Simulated deposit confirmed",
                             f"{tx['reference']}: simulated ETH deposit reached {REQUIRED_CONF} simulated confirmations.")
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
        "recipient_wallet_balance": 0.0, "created_at": now(), "invitations_sent_at": None,
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
    return tx


# ---------- transactions ----------
class TxCreate(BaseModel):
    usd_value: float
    sender_name: str
    recipient_name: str
    network: str = "Ethereum Mainnet (simulated only)"


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
    await log(tx, user, "Transaction created", f"{ref} — illustrative value {money(body.usd_value)}")
    return present(tx)


@api.get("/transactions/{tx_id}")
async def get_transaction(tx_id: str, user: dict = Depends(current_user)):
    return present(await load_tx(tx_id, user))


class ActionIn(BaseModel):
    data: Dict[str, Any] = {}


def need(cond: bool, msg: str):
    if not cond:
        raise HTTPException(400, msg)


@api.post("/transactions/{tx_id}/actions/{action}")
async def run_action(tx_id: str, action: str, body: ActionIn, user: dict = Depends(current_user)):
    tx = await load_tx(tx_id, user)
    d = body.data or {}
    is_admin = user["role"] == "admin"
    party = party_of(tx, user)
    step = current_step(tx)
    f = step_flags(tx)
    sets: Dict[str, Any] = {}
    need(not tx.get("completed_at") or action == "noop", "Transaction is already completed")
    if action not in ("hold", "resume"):
        need(not tx.get("on_hold"), "Transaction is on hold — an administrator must resume it")

    if action == "send_invitations":
        need(is_admin, "Administrator only")
        need(not f[1], "Invitations already sent")
        sets["invitations_sent_at"] = now()
        await notify(tx, ["sender"], f"Escrow invitation — {tx['reference']}",
                     f"You are invited by VaultBridge Escrow (simulated) to participate as SENDER for {tx['reference']} on behalf of {tx['sender_name']}. Illustrative value {money(tx['usd_value'])}. Open the Overview to accept or decline.", "email")
        await notify(tx, ["recipient"], f"Escrow invitation — {tx['reference']}",
                     f"You are invited by VaultBridge Escrow (simulated) to participate as RECIPIENT for {tx['reference']} on behalf of {tx['recipient_name']}. Illustrative value {money(tx['usd_value'])}. Open the Overview to accept or decline.", "email")
        msg = "Simulated invitation emails sent to sender and recipient"
    elif action == "resend_invitation":
        need(is_admin, "Administrator only")
        p = d.get("party")
        need(p in ("sender", "recipient") and tx["invitations"][p]["status"] == "declined", "No declined invitation for that party")
        sets[f"invitations.{p}"] = {"status": "pending", "responded_at": None}
        await notify(tx, [p], f"Escrow invitation re-sent — {tx['reference']}", "The administrator has re-issued your simulated escrow invitation.", "email")
        msg = f"Invitation re-sent to {p}"
    elif action in ("accept_invitation", "decline_invitation"):
        need(party is not None, "Only an invited party can respond")
        need(f[1], "Invitations have not been sent yet")
        need(tx["invitations"][party]["status"] == "pending", "Invitation already answered")
        status = "accepted" if action == "accept_invitation" else "declined"
        sets[f"invitations.{party}"] = {"status": status, "responded_at": now()}
        await notify(tx, ["admin"], f"Invitation {status} by {party}", f"{tx['reference']}: the {party} has {status} the escrow invitation.")
        msg = f"{party.capitalize()} {status} invitation"
    elif action == "submit_onboarding":
        need(party is not None, "Only a party can submit onboarding")
        need(tx["invitations"][party]["status"] == "accepted", "Accept the invitation first")
        need(tx["onboarding"][party]["status"] in ("not_started", "rejected"), "Onboarding already submitted")
        required = ["legal_name", "registration_number", "jurisdiction", "contact_name", "contact_email", "wallet_address"]
        need(all(str(d.get(k, "")).strip() for k in required), "All onboarding fields are required")
        w = str(d["wallet_address"]).strip()
        need(w.startswith("0x") and len(w) == 42, "Simulated wallet address must be 0x followed by 40 hex characters")
        need(bool(d.get("fictional_confirmed")), "Confirm the data is fictional demonstration data")
        data = {k: str(d.get(k, "")).strip() for k in required + ["beneficial_owner", "business_description"]}
        sets[f"onboarding.{party}"] = {"status": "submitted", "data": data, "submitted_at": now(), "reviewed_at": None, "note": ""}
        await notify(tx, ["admin"], f"Onboarding submitted by {party}", f"{tx['reference']}: {party} submitted simulated onboarding for review.")
        msg = f"{party.capitalize()} submitted simulated onboarding"
    elif action == "review_onboarding":
        need(is_admin, "Administrator only")
        p, decision = d.get("party"), d.get("decision")
        need(p in ("sender", "recipient") and decision in ("approved", "rejected"), "Invalid review")
        need(tx["onboarding"][p]["status"] == "submitted", "Onboarding is not awaiting review")
        sets[f"onboarding.{p}.status"] = decision
        sets[f"onboarding.{p}.reviewed_at"] = now()
        sets[f"onboarding.{p}.note"] = str(d.get("note", ""))
        await notify(tx, [p], f"Onboarding {decision} (simulated)", f"{tx['reference']}: your simulated onboarding was {decision}. {d.get('note', '')}")
        msg = f"Onboarding for {p} {decision} (simulated)"
    elif action == "issue_agreement":
        need(is_admin, "Administrator only")
        need(step == 6, "Both onboardings must be submitted first")
        need(all(tx["onboarding"][p]["status"] == "approved" for p in ("sender", "recipient")), "Approve both onboardings first")
        sets["agreement.issued_at"] = now()
        await notify(tx, ["sender", "recipient"], "Escrow agreement ready for review", f"{tx['reference']}: the simulated escrow agreement is available for your review and acceptance.")
        msg = "Simulated escrow agreement issued for review"
    elif action == "accept_agreement":
        need(party is not None, "Only a party can accept the agreement")
        need(step == 7, "Agreement is not open for acceptance")
        need(not tx["agreement"].get(f"{party}_accepted_at"), "Already accepted")
        need(bool(d.get("confirmed")), "Confirm you have reviewed the simulated terms")
        sets[f"agreement.{party}_accepted_at"] = now()
        await notify(tx, ["admin"], f"Agreement accepted by {party}", f"{tx['reference']}: {party} accepted the simulated escrow agreement.")
        msg = f"{party.capitalize()} accepted the simulated escrow agreement"
    elif action == "initiate_deposit":
        need(party == "sender", "Only the sender can initiate the deposit")
        need(step == 11, "Deposit is not open yet")
        need(bool(d.get("confirmed")), "Confirm the simulated deposit")
        sets["deposit"] = {
            "initiated_at": now(), "confirmations": 0, "required": REQUIRED_CONF,
            "from_address": tx["onboarding"]["sender"]["data"]["wallet_address"], "to_address": tx["escrow_vault_address"],
            "eth_quantity": tx["eth_quantity"], "tx_hash": sim_hash(), "block_number": random.randint(21_400_000, 21_900_000),
            "network_fee_eth": round(random.uniform(0.0021, 0.0068), 6), "gas_used": random.randint(21000, 64000),
        }
        sets["sender_wallet_balance"] = round(tx["sender_wallet_balance"] - tx["eth_quantity"], 6)
        await notify(tx, ["recipient", "admin"], "Simulated ETH deposit initiated", f"{tx['reference']}: sender initiated a simulated deposit of {eth(tx['eth_quantity'])}.")
        msg = f"Simulated deposit of {eth(tx['eth_quantity'])} initiated"
    elif action == "generate_analysis":
        need(is_admin, "Administrator only")
        need(step == 13, "Deposit must be fully confirmed first")
        sets["analysis"] = {
            "generated_at": now(), "risk_score": random.randint(8, 22), "risk_band": "Low (simulated)",
            "hops_analysed": 5, "counterparties_traced": random.randint(14, 40),
            "exposure": [
                {"category": "Fictional institutional exchange", "percent": 62.4},
                {"category": "Fictional OTC desk", "percent": 21.3},
                {"category": "Fictional custodian wallets", "percent": 14.1},
                {"category": "Unattributed (fictional)", "percent": 2.2},
                {"category": "Sanctioned / high-risk (fictional)", "percent": 0.0},
            ],
            "provider": "VaultBridge Demonstration Analytics Engine (fictional)",
        }
        sets["compliance.wallet_risk.status"] = "Under Review"
        sets["compliance.tx_monitoring.status"] = "Under Review"
        await notify(tx, ["sender", "recipient"], "Simulated blockchain analysis generated", f"{tx['reference']}: a fictional blockchain analysis is available in the Blockchain Explorer.")
        msg = "Simulated blockchain analysis generated"
    elif action == "set_compliance":
        need(is_admin, "Administrator only")
        k, s = d.get("check"), d.get("status")
        need(k in tx["compliance"] and s in COMPLIANCE_STATUSES, "Invalid compliance update")
        need(not tx["aml"].get("completed_at"), "AML review already completed")
        sets[f"compliance.{k}"] = {"label": tx["compliance"][k]["label"], "status": s, "note": str(d.get("note", "")), "updated_at": now()}
        msg = f"{tx['compliance'][k]['label']} set to {s}"
    elif action == "complete_aml":
        need(is_admin, "Administrator only")
        need(step == 14, "Blockchain analysis must be generated first")
        need(all(c["status"] == "Simulated Approval" for c in tx["compliance"].values()), "All 7 checks must be at Simulated Approval")
        sets["aml.completed_at"] = now()
        await notify(tx, ["sender", "recipient"], "Simulated AML review completed", f"{tx['reference']}: demonstration verification reports are now available in Reports.")
        msg = "Simulated AML review completed"
    elif action == "request_settlement":
        need(party == "sender" or is_admin, "Only the sender or administrator can initiate settlement")
        need(step == 16 and not tx["settlement"].get("requested_at"), "Settlement cannot be requested now")
        sets["settlement"] = {"status": "requested", "requested_at": now(), "requested_by": user["email"], "release_eth": tx["eth_quantity"]}
        await notify(tx, ["recipient", "admin"], "Simulated settlement request", f"{tx['reference']}: a settlement request to release {eth(tx['eth_quantity'])} was initiated. Recipient acknowledgement required.")
        msg = "Simulated settlement request initiated"
    elif action == "acknowledge_settlement":
        need(party == "recipient", "Only the recipient can approve the request")
        need(step == 16 and tx["settlement"].get("requested_at") and not tx["settlement"].get("recipient_acknowledged_at"), "No settlement request awaiting recipient approval")
        sets["settlement.recipient_acknowledged_at"] = now()
        sets["settlement.status"] = "awaiting_admin"
        await notify(tx, ["admin", "sender"], "Recipient approved settlement request", f"{tx['reference']}: recipient approved the simulated settlement request. Awaiting administrator release.")
        msg = "Recipient approved the simulated settlement request"
    elif action == "decide_settlement":
        need(is_admin, "Administrator only")
        need(step == 17, "Settlement is not awaiting administrator decision")
        if d.get("decision") == "approved":
            sets["settlement.status"] = "released"
            sets["settlement.approved_at"] = now()
            sets["settlement.release_tx_hash"] = sim_hash()
            sets["settlement.release_block"] = random.randint(21_900_001, 22_100_000)
            await notify(tx, ["sender", "recipient"], "Simulated release approved", f"{tx['reference']}: administrator approved the simulated release. Recipient must accept the balance update.")
            msg = "Administrator approved simulated release"
        else:
            sets["settlement"] = {"status": "rejected", "rejected_at": now(), "note": str(d.get("note", ""))}
            await notify(tx, ["sender", "recipient"], "Simulated settlement rejected", f"{tx['reference']}: settlement request rejected. {d.get('note', '')} A new request may be initiated.")
            msg = "Administrator rejected simulated settlement request"
    elif action == "accept_balance":
        need(party == "recipient", "Only the recipient can accept the balance update")
        need(step == 18, "No released balance to accept")
        sets["settlement.credited_at"] = now()
        sets["recipient_wallet_balance"] = round(tx["recipient_wallet_balance"] + tx["eth_quantity"], 6)
        await notify(tx, ["admin", "sender"], "Recipient received simulated balance", f"{tx['reference']}: recipient simulated balance credited with {eth(tx['eth_quantity'])}.")
        msg = f"Recipient simulated balance credited with {eth(tx['eth_quantity'])}"
    elif action == "complete":
        need(is_admin, "Administrator only")
        need(step == 19, "All prior steps must be completed")
        sets["completed_at"] = now()
        await notify(tx, ["sender", "recipient"], "COMPLETED — SIMULATION", f"{tx['reference']} is complete. The final completion report is available.")
        msg = "Transaction status changed to COMPLETED — SIMULATION"
    elif action in ("hold", "resume"):
        need(is_admin, "Administrator only")
        sets["on_hold"] = action == "hold"
        msg = "Transaction placed on hold" if action == "hold" else "Transaction resumed"
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
    await log(None, user, "Demonstration fees updated", ", ".join(f"{i.label}: ${i.amount:,.0f}" for i in items))
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


@api.post("/invoices")
async def create_invoice(body: InvoiceIn, user: dict = Depends(admin_user)):
    tx = await load_tx(body.transaction_id, user)
    need(body.party in ("sender", "recipient") and body.items, "Choose a party and at least one fee item")
    need(not tx.get("on_hold") and not tx.get("completed_at"), "Transaction is not open for invoicing")
    fees = {i["code"]: i for i in (await db.settings.find_one({"key": "fees"}))["items"]}
    need(all(c in fees for c in body.items), "Unknown fee item")
    if body.kind == "engagement":
        need(body.party == "recipient", "Engagement invoice is issued to the recipient")
        need(current_step(tx) == 8, "Engagement invoice can only be issued once the agreement is accepted by both parties")
    n = await next_counter("invoice")
    lines = [{"code": c, "description": fees[c]["label"], "amount": fees[c]["amount"]} for c in body.items]
    inv = {
        "id": new_id(), "invoice_number": f"VB-INV-2026-{n:04d}", "transaction_id": tx["id"], "reference": tx["reference"],
        "kind": body.kind, "party": body.party,
        "responsible_name": tx[f"{body.party}_name"], "responsible_user_id": tx[f"{body.party}_user_id"],
        "items": lines, "amount": sum(l["amount"] for l in lines), "currency": "USD (fictional)",
        "status": "Issued", "issued_at": now(), "submitted_at": None, "paid_at": None,
    }
    await db.invoices.insert_one(dict(inv))
    if body.kind == "engagement":
        await db.transactions.update_one({"id": tx["id"]}, {"$set": {"payment.invoice_id": inv["id"]}})
    await notify(tx, [body.party], f"Simulated invoice {inv['invoice_number']}", f"{tx['reference']}: a demonstration invoice for ${inv['amount']:,.2f} (fictional) was issued to you.")
    await log(tx, user, f"Invoice {inv['invoice_number']} generated", f"{body.kind} invoice to {body.party} — ${inv['amount']:,.2f} (fictional)")
    return inv


async def load_invoice(inv_id: str, user: dict) -> dict:
    inv = await db.invoices.find_one({"id": inv_id}, {"_id": 0})
    if not inv or (user["role"] != "admin" and inv["responsible_user_id"] != user["id"]):
        raise HTTPException(404, "Invoice not found")
    return inv


@api.post("/invoices/{inv_id}/pay")
async def pay_invoice(inv_id: str, user: dict = Depends(current_user)):
    inv = await load_invoice(inv_id, user)
    need(user["id"] == inv["responsible_user_id"], "Only the responsible party can make the simulated payment")
    need(inv["status"] == "Issued", "Invoice is not awaiting payment")
    tx = await load_tx(inv["transaction_id"], user)
    need(not tx.get("on_hold"), "Transaction is on hold")
    ts = now()
    await db.invoices.update_one({"id": inv_id}, {"$set": {"status": "Payment Submitted (Simulated)", "submitted_at": ts, "payment_ref": "SIM-PAY-" + secrets.token_hex(4).upper()}})
    if inv["kind"] == "engagement":
        await db.transactions.update_one({"id": tx["id"]}, {"$set": {"payment.submitted_at": ts}})
    await notify(tx, ["admin"], f"Simulated payment submitted — {inv['invoice_number']}", f"{tx['reference']}: {inv['party']} submitted a simulated payment of ${inv['amount']:,.2f} (fictional). Confirmation required.")
    await log(tx, user, f"Simulated payment submitted for {inv['invoice_number']}", f"${inv['amount']:,.2f} (fictional) — no real funds moved")
    return await load_invoice(inv_id, user)


@api.post("/invoices/{inv_id}/confirm")
async def confirm_invoice(inv_id: str, user: dict = Depends(admin_user)):
    inv = await load_invoice(inv_id, user)
    need(inv["status"] == "Payment Submitted (Simulated)", "No simulated payment awaiting confirmation")
    tx = await load_tx(inv["transaction_id"], user)
    ts = now()
    await db.invoices.update_one({"id": inv_id}, {"$set": {"status": "Paid (Simulated)", "paid_at": ts}})
    if inv["kind"] == "engagement":
        await db.transactions.update_one({"id": tx["id"]}, {"$set": {"payment.confirmed_at": ts}})
    await notify(tx, [inv["party"]], f"Simulated payment confirmed — {inv['invoice_number']}", f"{tx['reference']}: administrator confirmed your simulated payment.")
    await log(tx, user, f"Simulated payment confirmed for {inv['invoice_number']}")
    return await load_invoice(inv_id, user)


@api.get("/invoices/{inv_id}/pdf")
async def invoice_pdf(inv_id: str, user: dict = Depends(current_user)):
    inv = await load_invoice(inv_id, user)
    sections = [
        ("Invoice", [("Invoice number", inv["invoice_number"] + " (SIMULATED)"), ("Transaction reference", inv["reference"]),
                     ("Responsible party", f"{inv['responsible_name']} ({inv['party']})"), ("Payment status", inv["status"]),
                     ("Date issued", inv["issued_at"][:19].replace("T", " ")), ("Date paid", (inv["paid_at"] or "—")[:19].replace("T", " "))]),
        ("Services (fictional amounts)", [(l["description"], money(l["amount"])) for l in inv["items"]] + [("TOTAL", money(inv["amount"]))]),
    ]
    pdf = build_report("Demonstration Invoice", inv["reference"], sections)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{inv["invoice_number"]}-SIMULATION.pdf"'})


# ---------- reports ----------
def report_sections(kind: str, tx: dict) -> list:
    base = [("Transaction reference", f"{tx['reference']} (SIMULATED)"), ("Asset", "ETH (simulated)"),
            ("Network", tx["network"]), ("Sender", tx["sender_name"]), ("Recipient", tx["recipient_name"]),
            ("Illustrative value", money(tx["usd_value"])), ("Illustrative ETH price", money(tx["eth_price"])),
            ("Simulated ETH quantity", eth(tx["eth_quantity"]))]
    dep, st, an = tx["deposit"], tx["settlement"], tx["analysis"]
    dep_rows = [("Simulated sending address", f"{dep.get('from_address')} (SIMULATED)"), ("Simulated escrow address", f"{dep.get('to_address')} (SIMULATED)"),
                ("Simulated transaction hash", f"{dep.get('tx_hash')} (SIMULATED)"), ("Simulated block number", dep.get("block_number")),
                ("Simulated confirmations", f"{dep.get('confirmations')}/{REQUIRED_CONF}"), ("Simulated network fee", eth(dep.get("network_fee_eth", 0))),
                ("Simulated timestamp", dep.get("initiated_at"))]
    if kind == "engagement":
        a = tx["agreement"]
        return [("Engagement summary", base), ("Agreement acceptance (simulated)", [
            ("Agreement issued", a["issued_at"]), ("Sender accepted", a["sender_accepted_at"]), ("Recipient accepted", a["recipient_accepted_at"])])]
    if kind == "deposit":
        return [("Transaction", base), ("Simulated deposit — not verifiable on Ethereum", dep_rows)]
    if kind == "blockchain_analysis":
        return [("Transaction", base[:1] + base[7:]), ("Simulated analysis", [
            ("Engine", an.get("provider")), ("Fictional risk score", f"{an.get('risk_score')}/100 — {an.get('risk_band')}"),
            ("Hops analysed", an.get("hops_analysed")), ("Counterparties traced (fictional)", an.get("counterparties_traced")),
            ("Generated", an.get("generated_at"))]), ("Fictional exposure breakdown", [(e["category"], f"{e['percent']}%") for e in an.get("exposure", [])])]
    if kind == "compliance":
        return [("Transaction", base[:5]), ("Simulated compliance outcomes — not real AML/KYC approvals",
                [(c["label"], f"{c['status']}{' — ' + c['note'] if c.get('note') else ''}") for c in tx["compliance"].values()]),
                ("Review", [("Simulated AML review completed", tx["aml"].get("completed_at"))])]
    if kind == "custody":
        return [("Transaction", base), ("Simulated custody position", [
            ("Simulated escrow address", f"{tx['escrow_vault_address']} (SIMULATED)"),
            ("Simulated held balance", eth(0 if st.get("approved_at") else tx["eth_quantity"])),
            ("Custody status", "Released (simulated)" if st.get("approved_at") else "Held in simulated escrow"),
            ("Deposit confirmed", dep.get("confirmed_at"))])]
    if kind == "settlement":
        return [("Transaction", base), ("Simulated settlement", [
            ("Requested by", st.get("requested_by")), ("Requested at", st.get("requested_at")),
            ("Recipient approved", st.get("recipient_acknowledged_at")), ("Administrator approved release", st.get("approved_at")),
            ("Simulated release hash", f"{st.get('release_tx_hash')} (SIMULATED)"), ("Simulated release block", st.get("release_block")),
            ("Released quantity", eth(st.get("release_eth", 0))), ("Recipient balance credited", st.get("credited_at") or "Pending")])]
    return [("Transaction", base), ("Deposit", dep_rows[:4]), ("Settlement", [
        ("Release hash", f"{st.get('release_tx_hash')} (SIMULATED)"), ("Recipient simulated balance", eth(tx["recipient_wallet_balance"])),
        ("Completed", tx.get("completed_at")), ("Final status", "COMPLETED — SIMULATION")]),
        ("Lifecycle", [(f"Step {i + 1}", t) for i, (t, _) in enumerate(STEPS)])]


@api.get("/reports/{tx_id}/{kind}/pdf")
async def report_pdf(tx_id: str, kind: str, user: dict = Depends(current_user)):
    tx = await load_tx(tx_id, user)
    meta = next((r for r in REPORT_TYPES if r[0] == kind), None)
    need(meta is not None, "Unknown report")
    need(step_flags(tx)[meta[2] - 1], "Report not yet available at this stage")
    party = party_of(tx, user)
    if party and kind in VERIFICATION_REPORTS and not tx["report_access"].get(party) and not tx.get("on_hold"):
        await db.transactions.update_one({"id": tx_id}, {"$set": {f"report_access.{party}": now()}})
        await notify(tx, ["admin"], f"Verification report accessed by {party}", f"{tx['reference']}: {party} accessed the {meta[1].lower()}.")
    await log(tx, user, f"Report downloaded: {meta[1]}")
    pdf = build_report(meta[1], tx["reference"], report_sections(kind, tx))
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{tx["reference"]}-{kind}-SIMULATION.pdf"'})


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
    await notify(tx, ["sender", "recipient"], "Demonstration report uploaded", f"{tx['reference']}: administrator uploaded '{doc['title']}' (demonstration document).")
    await log(tx, user, f"Demonstration report uploaded: {doc['title']}", file.filename)
    return {k: v for k, v in doc.items() if k not in ("_id", "content")}


@api.get("/reports/uploads/{up_id}/download")
async def download_upload(up_id: str, user: dict = Depends(current_user)):
    doc = await db.uploaded_reports.find_one({"id": up_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Not found")
    await load_tx(doc["transaction_id"], user)
    return Response(base64.b64decode(doc["content"]), media_type=doc["content_type"],
                    headers={"Content-Disposition": f'attachment; filename="SIMULATION-{doc["filename"]}"'})


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
    await log(None, user, "Demo environment reset", "All simulated records restored to initial state")
    return {"ok": True}


# ---------- seed ----------
DEMO_USERS = [
    {"email": "admin@vaultbridge.demo", "password": "AdminDemo#2026", "role": "admin", "name": "Alex Morgan (Demo Administrator)", "organisation": "VaultBridge Escrow (Simulated)"},
    {"email": "sender@vaultbridge.demo", "password": "SenderDemo#2026", "role": "sender", "name": "Jordan Hale (Demo Sender)", "organisation": "Demo Investment Entity"},
    {"email": "recipient@vaultbridge.demo", "password": "RecipientDemo#2026", "role": "recipient", "name": "Riley Chen (Demo Recipient)", "organisation": "Demo Acquisition Company"},
]


async def seed_users():
    users = list(DEMO_USERS)
    if os.environ.get("OWNER_EMAIL") and os.environ.get("OWNER_PASSWORD"):
        users.append({"email": os.environ["OWNER_EMAIL"].lower(), "password": os.environ["OWNER_PASSWORD"], "role": "admin",
                      "name": "Platform Owner (Administrator)", "organisation": "VaultBridge Escrow (Simulated)"})
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
        tx = await new_transaction("VB-ETH-2026-001", 6_000_000_000.0, "Demo Investment Entity", "Demo Acquisition Company", "Ethereum Mainnet (simulated only)")
        await log(tx, None, "Transaction created", "Default demonstration transaction VB-ETH-2026-001 — status Awaiting onboarding")


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
