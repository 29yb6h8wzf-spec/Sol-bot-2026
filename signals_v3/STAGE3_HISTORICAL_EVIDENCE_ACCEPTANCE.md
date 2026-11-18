# Stage 3 — historical funding and order-book evidence acceptance contract

Status: **BLOCKED — no provider-authenticated historical evidence approved** (2026-11-18).

This document is a research checklist, **not** a statement that any required archive exists, is complete, or has been verified. It does not authorize live trading, a deployment, a merge, or a positive performance claim.

## Current code behavior (verified in this branch)

- `historical_evidence_provenance.py` checks manifest structure, timestamps, path safety, artifact roles and SHA-256 integrity.
- Its accepted artifact roles are `point_in_time_listings` and `historical_orderbook`. Funding is **not** an accepted artifact role in the current verifier.
- A matching checksum only proves bytes match the supplied digest; the digest and source reference can be self-declared.
- Consequently `historical_evidence_verified`, `provider_authenticity_verified`, `historical_market_coverage_verified`, `funding_history_verified`, `orderbook_history_verified`, and `point_in_time_universe_verified` all remain **False**.
- `replay_verified_historical_universe` correctly fails closed if those independent attestations are not true. Do **not** flip them to True based on manifest flags.

## Acceptance criteria before any verified replay

1. **Provider authenticity:** independently recoverable provider/exchange source, immutable retrieval reference, capture time, acquisition method, raw file hashes, and verification procedure; do not treat user-written source references as proof.
2. **Funding history:** instrument, exchange, exact funding event UTC timestamp, rate, provenance, interval rules and coverage of every requested evaluation period; gaps explicitly recorded.
3. **Historical order book:** timestamped depth/spread evidence at or before each decision timestamp, exchange/instrument identity, sampling interval, raw levels or reproducible derived metrics, and no future-data leakage.
4. **Point-in-time universe:** listing/delisting and eligibility at each decision time, including symbols not ultimately selected. Current exchangeInfo snapshots do not prove past listings.
5. **Coverage audit:** expected decision schedule vs observed timestamps, duplicates, missing windows, stale samples, time-zone normalization, and source-specific outage windows.
6. **Independent cross-check:** at least one independently acquired reference for timestamps and representative funding/depth records; differences recorded, not silently filled.
7. **Costs:** funding cash flows, maker/taker fees, slippage and latency separately accounted for; any missing component marks full-net results inconclusive.
8. **Reproducibility:** lock raw hashes, acquisition scripts, validation code commit, run configuration and rejection counts before reading performance results.

## Next engineering steps

- Define a separate **integrity-only** funding artifact contract with offline fixtures and negative tests. Do not change the current authenticated-evidence gate to True.
- Inventory actual archive objects and their provenance **read-only**. No download, secret access, or cloud execution is implied by this document.
- Add deterministic coverage and point-in-time timestamp tests. Any missing historical depth/funding keeps verified replay blocked.
- Run offline CI on the research branch. Merge and deployment require separate owner authorization.

## Explicit non-claims

Passing offline CI is not evidence of a profitable trading edge. Existing SOL/XRP replay results must not be promoted to out-of-sample evidence. Until the above checks pass independently, the historical verified replay remains unavailable by design.
