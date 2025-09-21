# Peer Review – Escrow Smart Contract for Ride‑Sharing

## Introduction

This document provides a peer review of the escrow smart contract developed with iKing for a ride‑sharing service on the Cardano blockchain. The contract’s primary purpose is to securely hold ADA funds until predefined conditions for the ride are met.

## Architecture & Flow (High‑Level)

The escrow is designed around a strict **separation of concerns** to keep components small, testable, and maintainable.

**On‑chain / Scripted Actions**
1. **Lock** – Accept ADA into escrow with a datum binding funds to a ride intent.
2. **Unlock (Payout)** – Release funds when the ride’s completion conditions are met.
3. **Refund (Fallback)** – Return funds to the payer when expiry/cancellation conditions are met.

**Off‑chain / Infrastructure**
- Distinct Python entry points for lock and unlock (and future refund) to preserve modularity.
- A thin coordination layer (CLI/API) may orchestrate user flows **without merging** the scripts, so we keep modular code while still giving unified UX.
- Clear, structured transaction logs that mirror contract state transitions (e.g., `Locked → In‑Ride → Completed → Unlocked` or `Refunded`).

## Current State of the Contract

- The contract currently allows locking and unlocking of ADA.
- Separate scripts are used to handle locking and unlocking actions.
- A basic redeem message exists but does not yet incorporate trip details, driver identity, or passenger information.
- Transaction logging is implemented, displaying actions taken and outputs generated.

## Suggestions for Improvement

- **Preserve Separation of Concerns (keep scripts separate):** Maintain distinct locking and unlocking (and future refund) scripts. This keeps the codebase modular, easier to reason about, and safer to change. Each script should do one thing well.
- **Add a unified *interface* (not a unified script):** Provide a thin CLI/API layer that offers a single user flow with consistent prompts and feedback while delegating to the separate lock/unlock/refund scripts under the hood.
- Expand the redeem logic in future versions to utilize trip information, driver identity, and passenger data to ensure correct combined ADA redemption.
  - Define a canonical redeemer schema (tripId, driverId, passengerId, fare components, signatures).
  - Support batching/multi‑leg trips so multiple partial payments can be atomically redeemed when completion criteria are met.
  - Add guardrails (timeouts, min/max fare checks, replay protection) before releasing funds.
- Enhance transaction logs to be more descriptive and closely tied to the trip’s state and payment milestones.
  - Emit structured logs (JSON/CSV) with: timestamp, action, txId, datum/redeemer hashes, participant IDs, tADA amount, and resulting state.
  - Mirror state transitions explicitly (e.g., `LOCKED`, `IN_RIDE`, `COMPLETED`, `UNLOCKED`, `REFUNDED`).
  - Store logs in an append‑only file and optionally a lightweight database for analytics and audit.
- Improve clarity and user-friendliness of feedback messages presented to users.
- Consider potential security and scalability challenges as the system usage increases.
  - Security: input validation, datum/redeemer integrity checks, signature/ownership verification, policy for refunds and time‑locks.
  - Scalability: optimize UTxO selection, minimize on‑chain bytes, and plan for congestion (fee estimation, backoff/retry).
  - Observability: add health checks and metrics (success rate, avg confirmation time, failure reasons).

## Testing & QA

- **Unit tests** for lock/unlock/refund paths (happy/edge/error cases).
- **Property tests** for invariants (e.g., funds conservation per tripId).
- **Integration tests** on preview/testnet with mocked trip states.
- **Negative tests** (bad redeemer, stale datum, signature mismatch, expired ride).
- **Acceptance checks**: clear console prompts, correct CSV rows, and accurate printed/returned amounts.

## Developer & User Experience

- Consistent CLI flags and prompts across scripts (e.g., `--amount`, `--trip-id`, `--driver-id`).
- Dry‑run mode that prints the planned transaction and log entry before submission.
- Helpful errors that suggest next steps (e.g., “ride not completed – try refund after <expiry>”).

## Roadmap (Near‑Term)

1. Keep lock/unlock as separate scripts; add a dedicated refund script.
2. Introduce a unified CLI/API wrapper for end‑to‑end flows.
3. Adopt a versioned redeemer schema carrying trip/driver/passenger metadata.
4. Implement structured JSON logs and state transition tracking.
5. Expand tests (unit/property/integration) and publish runbooks.

## Conclusion

The contract is functional and serves its intended purpose. However, it can evolve to include richer features, clearer feedback, and improved usability for both drivers and passengers, ultimately enhancing the overall ride‑sharing experience.

## Reviewers

- Ezekiel Donkor - Programs Manager, Backend/API and Web3
- David Simeon - Software Lead
- Clifford Adusei - QA 
- Sidney Odoom - Web/Devops
- Emmanuel Teye - Frontend Developer
