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

- v4 Workflow rebuild (2026-11-07): onboarding starts with real invitation emails (Emergent managed Resend, from "VaultBridge Escrow"), which show the deal details, the escrow rules and an "Enter the escrow" link to login. The admin enters both parties' emails when creating a deal and invitations are sent automatically (re-send from Home). New 10 steps: sender joins (accepts rules) → recipient joins → both pay the 2 ETH onboarding fee (admin-configurable) → admin approves & opens the escrow → sender deposits → admin AML checks → admin uploads AML/forensic docs on Forensics and releases the AML report (parties can't see the docs before release) → recipient requests funds → recipient withdrawal AML & escrow fees → admin releases funds. Tested iteration_4: 100% backend/frontend; minor fixes applied after (hex wallet check, fee > 0, no early forensic-upload notice, no duplicate invites to joined parties).
- Payments (onboarding fee, escrow fee) remain in-app payment records; no real funds are collected.

## Backlog
- v7 (2026-11-07): Escrow fees split 50/50. When the recipient requests the funds, two ETH invoices are created, one per party, each worth half the dollar fees (~$1.31M) converted at the live Etherscan ETH price. Each party pays to the admin wallet, either verified by tx hash or marked paid and then confirmed by the admin. The FeeSplit panel shows both parties' status to everyone. The admin can release only once both halves are confirmed or verified; the release tx hash is optional and verified if given. Deposit: the escrow wallet is the admin wallet (set at approval), verified by hash or confirmed by the admin; no fake confirmations or hashes. New deals use the live ETH price. The AML report uses the real sender wallet scan. Launch cleanup: admin demo card and DEMO badge removed, Reset demo endpoint and UI removed, random wallet generator removed from the join form. Tested in iteration_7; the issues it found were fixed and checked afterwards.
- v6 (2026-11-07): Onboarding fee pay-to wallet. The admin sets one receiving wallet in the Onboarding fee panel on the Payments page. Parties see "Send exactly X ETH to <wallet>", with a copy button. Two ways to pay: (a) paste the transaction hash, which is checked live on Etherscan mainnet. The transaction must go to the fee wallet, carry at least the fee, be mined and successful, be sent after the invoice was issued, and not have been used before (enforced by a unique index). It is then marked Paid automatically, with an Etherscan link, and the admin is warned if it came from a wallet other than the party's registered one. (b) "I've paid — admin will confirm" (Payment Sent → admin Confirm / Approve). No wallet set yet → parties can't pay. Tested in iteration_6; the security fixes were checked afterwards.
- v5 (2026-11-07): Invite-gated sign-up. The "Enter the escrow" link opens /login?email=… with the email filled in. The login page works in 2 steps: the user enters their email, then signs in if they have an account, or creates one (name + password) if the email was invited to a deal and has no account yet. A new account is linked to every deal that email was invited to, with the role from the invitation. Deal creation rejects the same email for both parties and emails already registered under another role, and nothing is saved when it fails. Automatic Etherscan wallet scan when a party joins: risk band/score, sanctions match and a PDF report are shown to the admin on the "Approve both parties" step, with a "Scan again" button if the scan fails. Tested in iteration_5; the issues it found were fixed and checked afterwards.
- P1: Multiple sender/recipient demo accounts per transaction
- P2: CSV export of audit logs; per-transaction fee overrides

## Next tasks
- Await user feedback
