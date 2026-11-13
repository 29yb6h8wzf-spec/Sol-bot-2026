# Stage 3 evidence update, 2026-11-13

The owner reports that results for every month from November 2024 through October 2026 inclusive were inspected on 2026-11-10. The entire 24-month window is therefore eligible only for exploratory analysis or reproduction. No subset, including May–October 2026, qualifies as a locked out-of-sample evaluation. The 18+6 months in research_plan.json describe a design. The plan records locked_oos as false.

## Reported replay

Source: Claude Code diagnostic supplied by the owner on 2026-11-13. These numbers were transcribed, without an independent replay. The diagnostic used SOLUSDT and XRPUSDT in December 2024, April, August and December 2025, and April and August 2026. Gross omits fees, slippage and funding. Net uses the diagnostic's existing 5-minute stop-first replay. R measures return relative to initial trade risk.

| Strategy | Trades | Mean gross R | Reported 95% interval, gross R | Mean net R |
| --- | ---: | ---: | ---: | ---: |
| trend_pullback | 598 | -0.0655 | [-0.177, +0.046] | -0.646 |
| liquidity_reversal | 173 | -0.0489 | [-0.255, +0.158] | -0.947 |
| volatility_breakout | 82 | +0.2066 | [-0.091, +0.504] | -0.106 |
| All | 853 | -0.0359 | [-0.129, +0.057] | -0.6549 |

The original run 43122294315 reported 852 trades. Its five-candle exclusion manifest was unavailable to the diagnostic, leaving the one-trade discrepancy unresolved. Resolving exits on one-minute bars yielded -0.6517R per trade. Four five-minute bars had ambiguous exits among the 853 trades.

## Decision status

The recommendation is to retire the current trend_pullback and liquidity_reversal variants. Formal closure remains the owner's decision. volatility_breakout remains unproven. Any independent evaluation requires a preregistered protocol and previously uninspected observations, with net expectancy as the primary outcome. No new test has been registered or run as part of this update.
