import asyncio
import logging
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

import httpx

logging.getLogger("httpx").setLevel(logging.WARNING)
BASE = "https://api.etherscan.io/v2/api"
OFAC_URL = "https://raw.githubusercontent.com/0xB10C/ofac-sanctioned-digital-currency-addresses/lists/sanctioned_addresses_ETH.txt"
ADDR = re.compile(r"^0x[a-fA-F0-9]{40}$")
WEI = Decimal(10) ** 18
MAX_TX = 1000
SPAM = re.compile(r"(https?://|www\.|\.com|\.io|\.org|\.xyz|visit|claim|reward|airdrop|\$)", re.I)

RISKY_SERVICES = {
    "0x722122df12d4e14e13ac3b6895a86e84145b6967": "Tornado Cash: Router",
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b": "Tornado Cash: Router (old)",
    "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc": "Tornado Cash: 0.1 ETH pool",
    "0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936": "Tornado Cash: 1 ETH pool",
    "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf": "Tornado Cash: 10 ETH pool",
    "0xa160cdab225685da1d56aa342ad8841c3b53f291": "Tornado Cash: 100 ETH pool",
    "0xd4b88df4d29f5cedd6857912842cff3b20c8cfa3": "Tornado Cash: 100 DAI pool",
    "0xfd8610d20aa15b7b2e3be39b396a1bc3516c7144": "Tornado Cash: 1,000 DAI pool",
    "0x07687e702b410fa43f4cb4af7fa097918ffd2730": "Tornado Cash: 10,000 DAI pool",
    "0x23773e65ed146a459791799d01336db287f25334": "Tornado Cash: 100,000 DAI pool",
    "0x8589427373d6d84e98730d7795d8f6f8731fda16": "Tornado Cash: Donation",
    "0x169ad27a470d064dede56a2d3ff727986b15d52b": "Tornado Cash: Mining",
    "0x905b63fff465b9ffbf41dea908ceb12478ec7601": "Tornado Cash: Proxy",
    "0x098b716b8aaf21512996dc57eb0615e2383e2f96": "Lazarus Group (Ronin exploit)",
    "0xa0e1c89ef1a489c9c7de96311ed5ce5d32c20e4b": "Lazarus Group",
    "0x3cffd56b47b7b41c56258d9c7731abadc360e073": "Lazarus Group",
    "0x53b6936513e738f44fb50d2b9476730c0ab3bfc1": "Lazarus Group",
}

_ofac: Dict[str, object] = {"set": set(), "loaded_at": 0.0, "source": OFAC_URL}
_gate = asyncio.Lock()
_last_call = [0.0]


def valid(address: str) -> bool:
    return bool(ADDR.fullmatch(address or ""))


async def _throttle():
    async with _gate:
        wait = 0.36 - (time.monotonic() - _last_call[0])
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call[0] = time.monotonic()


async def _call(http: httpx.AsyncClient, module: str, action: str, **params):
    q = {"chainid": "1", "module": module, "action": action, "apikey": os.environ["ETHERSCAN_API_KEY"], **params}
    for attempt in range(3):
        await _throttle()
        r = await http.get(BASE, params=q)
        r.raise_for_status()
        body = r.json()
        if module == "proxy":
            res = body.get("result")
            if isinstance(res, str) and "rate limit" in res.lower() and attempt < 2:
                await asyncio.sleep(1.2)
                continue
            if isinstance(res, str) and not res.startswith("0x"):
                raise RuntimeError(f"Etherscan: {res}")
            return res
        if body.get("status") == "1":
            return body["result"]
        msg = str(body.get("result") or body.get("message") or "")
        if "rate limit" in msg.lower() and attempt < 2:
            await asyncio.sleep(1.2)
            continue
        if "no transactions" in msg.lower() or body.get("message") == "No transactions found":
            return []
        if action in ("addresstokenbalance", "getaddresstag"):
            return []
        raise RuntimeError(f"Etherscan: {msg}")
    return []


TX_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")


async def verify_payment(tx_hash: str, to_addr: str, min_eth: float, not_before: datetime, what: str = "fee") -> dict:
    async with httpx.AsyncClient(timeout=20) as http:
        t = await _call(http, "proxy", "eth_getTransactionByHash", txhash=tx_hash)
        if not isinstance(t, dict):
            raise ValueError("Transaction not found on Ethereum mainnet")
        if (t.get("to") or "").lower() != to_addr.lower():
            raise ValueError(f"This transaction was not sent to {to_addr}")
        value = int(t["value"], 16) / 1e18
        if value + 1e-9 < min_eth:
            raise ValueError(f"This transaction sent {value:.4f} ETH; the {what} is {min_eth:g} ETH")
        if not t.get("blockNumber"):
            raise ValueError("The transaction is still pending — try again once it's mined")
        rc = await _call(http, "proxy", "eth_getTransactionReceipt", txhash=tx_hash)
        if not isinstance(rc, dict) or rc.get("status") != "0x1":
            raise ValueError("This transaction failed on-chain")
        blk = await _call(http, "proxy", "eth_getBlockByNumber", tag=t["blockNumber"], boolean="false")
        mined = datetime.fromtimestamp(int(blk["timestamp"], 16), timezone.utc)
        if mined < not_before:
            raise ValueError("This transaction was sent before this payment was requested — send a new payment and paste its hash")
    return {"from": t["from"], "value_eth": value, "block": int(t["blockNumber"], 16), "mined_at": mined.isoformat()}


async def eth_price() -> float:
    async with httpx.AsyncClient(timeout=15) as http:
        r = await _call(http, "stats", "ethprice")
    return float(r["ethusd"])


async def load_ofac(http: httpx.AsyncClient) -> set:
    if _ofac["set"] and time.time() - _ofac["loaded_at"] < 6 * 3600:
        return _ofac["set"]
    try:
        r = await http.get(OFAC_URL, timeout=20)
        r.raise_for_status()
        addrs = {line.strip().lower() for line in r.text.splitlines() if valid(line.strip())}
        if addrs:
            _ofac.update(set=addrs, loaded_at=time.time())
    except httpx.HTTPError:
        pass
    if not _ofac["set"]:
        raise RuntimeError("sanctions list is temporarily unavailable, please try again")
    return _ofac["set"]


def _eth(wei) -> float:
    return float(Decimal(int(wei or 0)) / WEI)


def _iso(ts) -> Optional[str]:
    return datetime.fromtimestamp(int(ts), timezone.utc).isoformat() if ts else None


def _flows(address: str, txs: List[dict], value_key=lambda t: _eth(t.get("value"))):
    inbound = outbound = 0.0
    n_in = n_out = 0
    parties = defaultdict(lambda: {"in": 0.0, "out": 0.0, "count": 0})
    for t in txs:
        if t.get("isError") == "1":
            continue
        frm, to, v = (t.get("from") or "").lower(), (t.get("to") or "").lower(), value_key(t)
        if to == address:
            inbound += v
            n_in += 1
            parties[frm]["in"] += v
            parties[frm]["count"] += 1
        elif frm == address:
            outbound += v
            n_out += 1
            if to:
                parties[to]["out"] += v
                parties[to]["count"] += 1
    return inbound, outbound, n_in, n_out, parties


async def analyse(address: str) -> dict:
    address = address.lower()
    async with httpx.AsyncClient(timeout=30) as http:
        sanctioned = await load_ofac(http)
        balance = await _call(http, "account", "balance", address=address, tag="latest")
        common = dict(address=address, startblock=0, endblock=99999999, page=1, offset=MAX_TX, sort="desc")
        normal = await _call(http, "account", "txlist", **common)
        internal = await _call(http, "account", "txlistinternal", **common)
        tokens = await _call(http, "account", "tokentx", **common)
        code = await _call(http, "proxy", "eth_getCode", address=address, tag="latest")

    n_in_eth, n_out_eth, n_in, n_out, parties = _flows(address, normal)
    i_in, i_out, _, _, iparties = _flows(address, internal)
    for k, v in iparties.items():
        for f in ("in", "out", "count"):
            parties[k][f] += v[f]

    token_map = defaultdict(lambda: {"symbol": "", "name": "", "contract": "", "dec": 0, "in": Decimal(0), "out": Decimal(0), "transfers": 0})
    for t in tokens:
        dec = int(t.get("tokenDecimal") or 0)
        val = Decimal(int(t.get("value") or 0)) / (Decimal(10) ** dec)
        tk = token_map[t["contractAddress"].lower()]
        tk.update(symbol=t.get("tokenSymbol", ""), name=t.get("tokenName", ""), contract=t["contractAddress"].lower(), dec=dec)
        tk["transfers"] += 1
        if (t.get("to") or "").lower() == address:
            tk["in"] += val
            other = (t.get("from") or "").lower()
        else:
            tk["out"] += val
            other = (t.get("to") or "").lower()
        parties[other]["count"] += 1
    holdings = sorted(
        [{"symbol": v["symbol"], "name": v["name"], "contract": v["contract"], "received": float(v["in"]), "sent": float(v["out"]),
          "transfers": v["transfers"], "dec": v["dec"], "balance": None}
         for v in token_map.values() if not SPAM.search(f"{v['symbol']} {v['name']}")],
        key=lambda x: -x["transfers"])[:50]
    async with httpx.AsyncClient(timeout=30) as http:
        for h in holdings[:6]:
            try:
                raw = await _call(http, "account", "tokenbalance", contractaddress=h["contract"], address=address, tag="latest")
                h["balance"] = float(Decimal(int(raw or 0)) / (Decimal(10) ** h["dec"]))
            except Exception:
                pass
    for h in holdings:
        h.pop("dec")

    stamps = [int(t["timeStamp"]) for t in normal + internal + tokens if t.get("timeStamp")]
    counterparties = sorted(
        [{"address": a, "received_eth": round(p["in"], 6), "sent_eth": round(p["out"], 6), "interactions": p["count"],
          "sanctioned": a in sanctioned, "service": RISKY_SERVICES.get(a)} for a, p in parties.items() if a and a != address],
        key=lambda x: -(x["received_eth"] + x["sent_eth"] + x["interactions"] / 1000))

    sanctioned_hits = [c for c in counterparties if c["sanctioned"]]
    risky_hits = [c for c in counterparties if c["service"]]
    self_sanctioned = address in sanctioned
    self_service = RISKY_SERVICES.get(address)
    failed = sum(1 for t in normal if t.get("isError") == "1")

    score, reasons = 0, []
    if self_sanctioned:
        score += 100
        reasons.append("Wallet itself appears on the OFAC sanctions list")
    if self_service:
        score += 80
        reasons.append(f"Wallet is a known high-risk service: {self_service}")
    if sanctioned_hits:
        score += min(60, 30 + 10 * len(sanctioned_hits))
        reasons.append(f"Direct interaction with {len(sanctioned_hits)} sanctioned address(es)")
    if risky_hits:
        score += min(40, 20 + 5 * len(risky_hits))
        reasons.append(f"Direct interaction with {len(risky_hits)} mixer / high-risk service address(es)")
    if not stamps:
        reasons.append("No on-chain history — insufficient data to assess source of funds")
        score += 10
    score = min(score, 100)
    band = "Severe" if score >= 80 else "High" if score >= 50 else "Medium" if score >= 20 else "Low"

    return {
        "address": address,
        "chain": "Ethereum Mainnet (chain id 1)",
        "is_contract": bool(code and code != "0x" and not str(code).startswith("0xef0100")),
        "delegated_7702": bool(code and str(code).startswith("0xef0100")),
        "balance_eth": _eth(balance),
        "activity": {
            "first_seen": _iso(min(stamps)) if stamps else None,
            "last_seen": _iso(max(stamps)) if stamps else None,
            "normal_tx": len(normal), "internal_tx": len(internal), "token_transfers": len(tokens),
            "failed_tx": failed, "eth_in": round(n_in_eth + i_in, 6), "eth_out": round(n_out_eth + i_out, 6),
            "tx_in": n_in, "tx_out": n_out, "unique_counterparties": len(counterparties),
            "history_capped": any(len(x) >= 1000 for x in (normal, internal, tokens)),
        },
        "tokens": holdings,
        "counterparties": counterparties[:25],
        "sanctions": {"listed": self_sanctioned, "counterparty_hits": sanctioned_hits, "list_size": len(sanctioned),
                      "list_source": "OFAC SDN digital currency addresses (ETH), via github.com/0xB10C/ofac-sanctioned-digital-currency-addresses",
                      "list_loaded_at": _iso(_ofac["loaded_at"]) if _ofac["loaded_at"] else None},
        "risky_services": {"self": self_service, "counterparty_hits": risky_hits},
        "risk": {"score": score, "band": band, "reasons": reasons or ["No sanctions or high-risk service exposure detected in direct interactions"]},
        "recent_transactions": [
            {"hash": t["hash"], "time": _iso(t["timeStamp"]), "from": t["from"], "to": t.get("to") or "(contract creation)",
             "value_eth": _eth(t.get("value")), "status": "Failed" if t.get("isError") == "1" else "Success"} for t in normal[:20]],
        "data_source": "Etherscan API V2 (live Ethereum mainnet data)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
