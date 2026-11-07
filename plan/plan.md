# VaultBridge Escrow — Admin can remove & re-invite a party

Give the administrator a way to take an already-onboarded sender or recipient off a deal and send a fresh
invitation — to a corrected email or a different person — so a deal that was set up with the wrong party can be fixed instead of abandoned.

## Who it's for
The escrow administrator, who today has no way to undo an onboarding. If the wrong email was invited or the wrong person
joined, the slot stays locked and no new invitation can be sent.

## Core features and experience
- **See who is on each deal.** For every deal, the admin sees each party slot (sender / recipient) with the invited
  email, the person's name, their join status (invited, joined, approved), and whether they have paid or deposited.
- **Remove a party from a deal.** On a slot, the admin picks "Remove & re-invite". This clears that one slot back to
  "awaiting invitation": the invitation and onboarding reset, any of that party's unpaid invoices for the deal are
  cancelled, and their wallet scan result is cleared. The other party and everything else on the deal are left untouched.
- **Optionally delete the account.** The admin can also delete the removed person's login account, which frees their
  email address so it can be invited again (or re-used elsewhere). Their past activity in the audit history is kept.
- **Send a fresh invitation.** After removal the slot is open, so the admin can enter any email (the same, a corrected
  one, or a different person) and the standard invitation email goes out again.
- **Safe by default.** Removal asks for a clear confirmation first and is blocked once the deal has moved past the point
  of no return (see Assumptions). The admin cannot delete their own account or any other administrator / the owner.

## User flow
1. Admin opens a deal and sees the two party slots with their current status.
2. Admin chooses "Remove & re-invite" on the party that is wrong, and confirms.
3. The slot resets to "awaiting invitation"; any unpaid invoice for that party is cancelled; the removed person loses
   access to the deal. If the admin also ticked "delete their account", that login is removed and the email is freed.
4. Admin enters the correct email for that slot and sends the invitation — the person receives the usual invite email
   and joins as normal.

## UI/UX feel
Matches the existing dark navy institutional dashboard. The party slots and the "Remove & re-invite" action live inside
the admin deal view, with a confirmation dialog that spells out exactly what will be cleared before anything happens.

## Implementation phases
**Phase 1 — MVP (built now):** Admin removes a party from a single deal, with the option to delete that account and free
the email, then re-invites a fresh email. Confirmation step, the safety guard, and protection of admin/owner accounts
are all included.

**Phase 2 (later):** A dedicated people/accounts view across all deals, re-assigning an already-registered user into a
slot without a new email, and a record of who was removed and when.

**Phase 3 (later):** Notify the removed party by email that they were taken off the deal, let the admin deactivate or
reset an account instead of deleting it, and let a party ask to be replaced.

## Assumptions
- Removal affects only the chosen slot on the chosen deal; the other party and all deal data are left as-is.
- Deleting an account frees that email for a new invitation. The person's audit-log entries and any saved forensic scans
  are kept for the record; only their login and deal links are removed.
- A party can be removed while the deal is still in onboarding or approval. Once the sender has deposited ETH (funds are
  in escrow) or the deal is completed, parties are locked and cannot be removed — this protects an in-flight escrow.
- Administrator and owner accounts cannot be deleted, and an admin cannot remove themselves.
- Re-inviting sends the same invitation email used today (deal details, escrow rules, and the "Enter the escrow" link).
- The rest of the platform — the onboarding fee at join, escrow fees paid after the deposit, on-chain verification — is
  left exactly as it works today; this upgrade only adds the remove-and-re-invite capability.
