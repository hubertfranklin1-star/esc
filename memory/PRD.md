# VaultBridge Escrow — PRD

## Original problem statement
VAULTBRIDGE ESCROW — FULL SIMULATION PLATFORM. Build a fully functional, interactive digital asset escrow simulation platform (simulation mode only: no real ETH, wallets, keys, custody, banking, charges, AML/KYC or certificates; persistent banner "SIMULATION ENVIRONMENT — NO REAL ASSETS OR PAYMENTS"). Three dashboards (Sender, Recipient, Administrator). Default transaction VB-ETH-2026-001, ETH, $6,000,000,000 illustrative, Demo Investment Entity → Demo Acquisition Company, Ethereum Mainnet (simulated only), status Awaiting onboarding. 19-step workflow (admin creates → invitations → accept → onboarding → agreement → engagement invoice → simulated payment → admin confirms → simulated deposit → confirmations → blockchain analysis → AML review → reports accessed → settlement request → admin approves release → recipient balance update → COMPLETED — SIMULATION), no auto-skipping. Configurable fee engine (7 fees), invoices, Ethereum-style explorer with confirmation animation, compliance centre (7 checks, 5 statuses, admin-editable), 7 watermarked PDF reports, premium dark navy institutional UI with 11-item left nav, demo login accounts shown on login page, persistent records, audit history.

User choices: ETH price fixed at $2,350; pre-filled sample fees; admin reset-demo button.

## Architecture
- Backend: FastAPI (`server.py`, `pdf_reports.py` via reportlab), MongoDB (users, transactions, invoices, audit_logs, notifications, uploaded_reports, settings, counters). JWT (bcrypt) demo auth with role guards. Workflow state machine via `step_flags`/`run_action`.
- Frontend: React + shadcn, AuthContext + TxContext (polling), role-aware NextActions bar on every page, 12 pages.

## Personas
Administrator (escrow agent), Sender (Demo Investment Entity), Recipient (Demo Acquisition Company).

## Implemented (2026-11-06)
- v2 simplification (user request): flow cut from 19 to 10 steps (join → approve → sign → pay fee → confirm → deposit → verify → request release → release); escrow fee invoice auto-created after both sign; single "What you need to do" card on Home; menu cut to Home, Deals, Payments, Documents, Checks (admin), Activity, Settings; all "simulated/fictional" wording removed (kept a small DEMO badge and a faint DEMO watermark/footer on PDFs as a minimal safeguard). Tested iteration_2: backend 12/12, frontend all flows pass; minor issues fixed after.
- Full 19-step lifecycle with role/order enforcement, decline/re-send, onboarding reject/resubmit, hold/resume
- Fee engine, invoices (engagement + standard), simulated pay/confirm, invoice PDFs
- Explorer with time-based 12 confirmations animation, simulated analysis, release tx
- Compliance centre, 7 report PDFs with SIMULATION watermark, admin uploads
- In-app inbox/notifications (simulated emails), audit logs, settings + reset
- Owner admin account (hubertfranklin1@gmail.com) not shown on login page
- Tested: iteration_1 — backend 100%, frontend 100%; minor issues fixed after

- v3 Forensics (2026-11-07): live on-chain wallet analysis via Etherscan API V2 (ETHERSCAN_API_KEY) — balance, token holdings (spam filtered, live balances for top tokens), transaction history, top counterparties, OFAC ETH address screening (0xB10C list mirror of OFAC SDN), mixer/Lazarus exposure, risk score; saved scans per user; PDF "On-Chain Forensic Analysis — Wallet Due-Diligence Report" (no demo watermark; footer states automated screening, not a certification). Tested iteration_3: backend 16/16, frontend pass. Licensed AML provider (Chainalysis/Elliptic) NOT built — needs a paid account.

## Backlog
- P1: Multiple sender/recipient demo accounts per transaction
- P2: CSV export of audit logs; per-transaction fee overrides

## Next tasks
- Await user feedback
