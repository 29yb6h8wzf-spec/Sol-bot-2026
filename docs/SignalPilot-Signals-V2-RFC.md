# SignalPilot Signals V2 — Research RFC 001
**Status:** DESIGN ONLY / RESEARCH ONLY / NO EXECUTION  
**Scope:** new signal engine for SOLUSDT and XRPUSDT; **do not change** `strategies.py`, `futures_engine/verified_strategy_scan.py`, `demo_independent_verifier.py`, `demo_order_planner.py`, `demo_execution_gate.py`, systemd, AWS services, Telegram production publisher, risk limits or exchange clients.  
**Owner preferences:** user questionnaire, 50/50, 2026-11-10. **Not a profitability claim.**

## 1. Non-negotiable user contract
- SOLUSDT and XRPUSDT only; LONG and SHORT; scan every 5 minutes.
- 5m primary, 1m confirmation. Intended holding time up to 4 hours (maximum 48 completed 5m bars), with shorter volatility-adaptive exits.
- Maximize *number of quality opportunities*, **not** raw signal count; no daily quota. Zero signals is valid if evidence is weak.
- Single hybrid engine with regime-aware strategy routing and coin-specific calibration/parameters; market regimes: TREND, RANGE/COMPRESSION, BREAKOUT/TRANSITION, HIGH_VOLATILITY, UNKNOWN. In RANGE wait for breakout; high volatility is a potential opportunity subject to spread, data quality and risk veto.
- Use market structure (HH/HL/LH/LL, BOS, CHoCH, support/resistance), liquidity sweep as optional confirmation, FVG and order blocks as research features; VWAP only for entry/exit context.
- Test EMA/ADX/RSI/MACD/candles/volume/Delta/CVD rather than requiring them by default.
- Free public data only. Test OI, funding, liquidations, depth imbalance; **never invent unavailable historical values**. Historical order book/CVD/liquidation coverage must be verified; prospective snapshots are required for claims about depth signals.
- Per-strategy thresholds, no inherited 85/100 hard gate in V2 research; display quality score **plus observed validation metrics**. Score is not a probability. Probability only after out-of-sample calibration.
- Probabilistic confirmation and ML from phase one **as a research competitor**, never as automatic order authority.
- Allow early-entry *research variants* with strict temporal validity and invalidation; default operational candidate requires completed 5m bars, with 1m confirmation from bars available at decision time. No incomplete 5m close-based feature leakage.
- Structure + ATR stop; dynamic target; minimum R:R selected from evidence; 1–2 5m bars validity after signal; adaptive holding time capped at 4h.
- Telegram format: entry, stop, target; optional evidence/score/metrics. Rejected signals go to a **separate research-only log/channel**, not an order path.
- Several simultaneous candidates permitted subject to pair correlation/exposure review **in research only**. Existing execution/risk policy remains unchanged.
- Warnings are permitted in **research alerts**. Missing critical inputs, stale feeds, negative net expectancy or unreliable probability always block executable eligibility. A warning must never override a hard safety veto.

## 2. Current repo reality / migration boundary
As of design inspection of main: `strategies.py` contains heuristic EMA_ADX, RSI_BOLL, MACD_VOLUME. `futures_engine/verified_strategy_scan.py` filters score >=85. `demo_independent_verifier.py` and `demo_order_planner.py` explicitly depend on `verified_85_score_engine` and independently verified 85+ proof. **V2 is a separate research namespace; do not silently swap those contracts.** Any future execution integration requires a separately reviewed versioned verifier/adapter, broker-independent proofs and dedicated authorization. This RFC does **not** modify, deploy or enable any execution.

## 3. Layered architecture
1. **Data contracts / as-of store**: timestamped, closed 1m and 5m OHLCV; symbol metadata; funding, OI, aggregated trades and order-book snapshots if available; UTC exchange/event timestamps and first-seen timestamps. Detect missing bars, duplicate bars, non-monotonic timestamps, stale or crossed books, and unavailable data. No forward fill across unobserved events.
2. **Features** (causal and independently testable): ATR, realized volatility, volatility compression, market structure with pivot confirmation delays, BOS/CHoCH, FVG/OB with deterministic rules, liquidity sweeps, VWAP, trend/momentum/volume, OI/funding; optional L2 imbalance and CVD only when event-time aligned and historically captured. Each feature records `available_at`.
3. **Regime classifier**: deterministic baseline first; compare learned regime classifier only with out-of-sample evidence. Emits regime, confidence, unknown reason; UNKNOWN => abstain. Regime decisions use prior/closed bars only.
4. **Three competing setup specialists** within one hybrid engine:
   - **Trend Continuation**: structure + trend direction, pullback/reclaim, momentum/volume confirmation.
   - **Breakout / Expansion**: compression, range break, volume and optional retest; no RANGE mean-reversion entries.
   - **Liquidity Reversal**: sweep + confirmed reclaim / CHoCH, optional FVG/OB, with high-volatility safeguards.
   Specialists output candidate hypotheses, not trades. Compare each to a deliberately simple baseline and to a rules-only ensemble.
5. **ML meta-labeler and probabilistic calibrator**: logistic regression baseline, gradient boosted trees candidate (e.g. XGBoost if available); compare to rules-only. Model predicts `P(net profitable exit under precommitted policy)` or `P(TP before SL before time barrier)` with the label precisely named; do **not** confuse with unconditional win probability. Calibrate on chronological calibration folds (isotonic/Platt), separately assess SOL/XRP and LONG/SHORT; low sample sizes => pooled/hierarchical or INCONCLUSIVE, never fabricated precision.
6. **Decision engine**: choose eligible specialist(s) based on regime and coin-specific validated parameters. Deduplicate same economic event and avoid contradictory directions. Apply expected net value (fees, slippage, funding), liquidity/spread veto, evidence sufficiency and strategy-specific thresholds fitted on training only. No daily quota. Do not optimize raw signal count at expense of net expectancy.
7. **Signal proposal**: entry zone, stop from confirmed structure plus ATR buffer, dynamic target from nearest valid liquidity/structure or volatility horizon, expected net R, adaptive time stop <=4h, valid-until = 1–2 completed 5m bars, invalidation rule. Always research-only until independent verification.
8. **Independent signal verifier / audit**: recompute features and proof from the same immutable as-of snapshot without importing the signal scorer; record dataset/model/config hashes, timestamp and rejection reasons. Any missing evidence fails closed. Separate research and approved alert schemas.

### Signal record (research-only; example field names, NOT an execution contract)
```json
{
  "schema_version": "signals.v2.research.1",
  "symbol": "SOLUSDT",
  "direction": "LONG",
  "strategy": "breakout_expansion",
  "regime": "BREAKOUT",
  "decision_time_ms": 0,
  "last_closed_5m_open_ms": 0,
  "one_minute_confirmation_until_ms": 0,
  "entry": null,
  "stop": null,
  "target": null,
  "valid_until_ms": 0,
  "max_holding_bars_5m": 48,
  "quality_score": null,
  "calibrated_probability": null,
  "calibration_sample_size": null,
  "oos_net_expectancy_r": null,
  "evidence_hash": null,
  "model_version": null,
  "config_hash": null,
  "status": "RESEARCH_ONLY",
  "execution_authorized": false,
  "orders_sent": false
}
```
`null` means unknown; **do not invent** probability, sample size, or trade prices. Only emit computed, validated values.

## 4. Scientific experiment matrix
| Family | Candidate tests | Independent comparison / caveat |
|---|---|---|
| Trend | EMA 9/21, 20/50, ADX 14, Supertrend | compare to structure-only; avoid redundant indicators |
| Momentum | RSI, MACD, ROC, divergences | ablation against trend/volume features |
| Breakout | Donchian, compression, volume-confirmed breakout, retest | distinguish true break vs fakeout; label availability at decision time |
| Structure/SMC | BOS, CHoCH, FVG, order blocks, liquidity sweeps | deterministic pivot-confirmation delay, no hindsight pivots |
| Volume | relative volume, OBV, MFI, VWAP entry context | exchange data quality and costs |
| Futures | OI, funding, trade delta, CVD, L2 imbalance, liquidations | no historical L2/liquidation backtest without archived as-of observations |
| Volatility | ATR, realized vol, compression/expansion, adaptive horizon | test both regime and stop-distance effects |
| ML | logistic, boosted trees, calibrated meta-labels, rules-only | strict chronological OOS; compare log loss, Brier, calibration and net PnL |

Every specialist has: `baseline`, `+one feature family`, `+full combination`, `-one family ablation`. Reject complexity when gain is not robust. Limit experiment budget and preregister candidates to mitigate multiple comparisons.

## 5. Data and leakage protocol
- Prefer 24 months of quality SOL/XRP 1m+5m Binance USD-M history if available, otherwise document actual coverage; 4h target requires at least 48 future 5m bars for matured labels. No imputation of missing trading periods.
- Historical train/validation/calibration/test splits are chronological, with purge/embargo at least 48 5m bars around split boundaries **plus any extra lookahead from label/feature design**. Keep final test untouched until configuration/model is frozen and commit-hashed.
- Nested walk-forward on development data for tuning; report performance separately in each locked OOS period and by coin, direction, regime and month. Account for correlated overlapping trades and non-independent events; avoid double-counting same bar/event.
- Triple-barrier labeling: proposed stop, proposed target, max holding time; same-candle stop+target ambiguity resolved conservatively (SL-first) unless timestamped 1m/tick sequence proves order. Timeouts receive actual mark-to-market exit minus costs, not silently counted as wins.
- Model training uses only features with `available_at <= decision_time`. Early-entry variants cannot use a not-yet-closed 5m bar as a closed-bar feature. Delayed OI/funding and pivot confirmations must respect publication/confirmation time.
- Simulate maker/taker fees according to actual execution assumption, spread, slippage, funding across hold and exchange filters; compare sensitivity under doubled costs. No use of unrealistic fills.
- Metrics: signal count/day, eligible fraction, TP/SL/time-out, win rate, **net expectancy per trade**, total net R, max drawdown, drawdown duration, profit factor, trade duration, turnover, calibration Brier/log-loss/reliability, precision by confidence bucket, CI with weekly block bootstrap; compare vs simple baseline.
- Selection: precommit thresholds and a minimum evidence gate; provisional target >=200 independent completed trade events total, >=8 weeks OOS and positive net expectancy in each of two locked OOS windows; insufficient sample => INCONCLUSIVE. These are **research acceptance rules**, not guarantees or statistical proof. Use multiple-testing correction / uncertainty-aware reporting.
- Reject any model that only wins in-sample, lacks cost-adjusted OOS improvement, or depends on unreproducible historical microstructure data.

## 6. Test matrix and acceptance gates
**T0 — contract**: 50 preferences encoded; old files unchanged; import graph contains no order client or AWS mutation.
**T1 — data**: gaps, duplicates, clock drift, 1m/5m close alignment, delayed funding/OI, unavailable L2, stale/crossed book.
**T2 — causal features**: no future candles, no hindsight BOS pivots, FVG/OB and sweep definitions deterministic, property tests for LONG/SHORT symmetry and stop orientation.
**T3 — specialists**: regime routing, no range reversal, volatility opportunity vs spread veto, per-coin parameters, conflicting signal dedup, 1–2-bar expiry.
**T4 — ML**: no train/test leakage, calibration only on allowed folds, abstain when calibration invalid, deterministic seeds and serialized model hash.
**T5 — historical simulator**: SL-first ambiguous candle, timeout, fees/funding/slippage, exchange min notional and precision, overlapping event handling, daily correlation attribution.
**T6 — OOS selection**: simple baselines, ablations, cost sensitivity, two locked periods, weekly bootstrap, multiple testing; INCONCLUSIVE if insufficient.
**T7 — shadow mode**: new signals logged read-only beside old pipeline for >=14 days with timestamped input snapshots and reason codes; no orders, no production Telegram replacement.
**T8 — review**: separate PR and approval for any future execution-adapter migration; independent verifier and risk gates remain untouched until that point.

## 7. Implementation plan (new files only)
1. `signals_v2/contracts.py`, `signals_v2/config.py`, `signals_v2/data.py`, `signals_v2/clock.py` + tests: immutable input/output schemas, as-of timestamps, strict feed validation.
2. `signals_v2/features/` + tests: market structure, ATR, volatility, trend, volume, optional derivatives/microstructure; implement deterministic, causal formulas.
3. `signals_v2/regime.py`, `signals_v2/specialists/{trend,breakout,liquidity}.py` + tests: independent setup hypotheses and regime router.
4. `signals_v2/research/{labels,simulator,splits,metrics,experiments}.py` + tests: chronological replay, realistic fees, funding, hold-time exits, walk-forward and locked OOS.
5. `signals_v2/ml/{baseline,boosted,calibration}.py` + tests: ML as competitor to rules, reproducibility and abstention.
6. `signals_v2/decision.py`, `signals_v2/verify.py`, `signals_v2/shadow.py` + tests: dynamic selection, independently checked research-only outputs, separate rejected research log.
7. Run shadow scan every 5m in **isolated** non-order environment only after review; evaluate evidence, then separately propose adapter. Do not merge/deploy/change systemd in this RFC.

### Explicit no-go conditions
No claim of profitability or calibrated accuracy without OOS results; no live trading; no Demo order writes; no silent replacement of 85+ independent verifier; no secret handling; no leverage/risk change; no mixing warnings with execution authorization; no new paid data services.

## 8. Questionnaire traceability
Q1 high-quality opportunities; Q2 <=4h; Q3 SOL/XRP; Q4 5m; Q5 both directions; Q6 hybrid; Q7 wait for breakout in range; Q8 trade high volatility when valid; Q9 per-coin; Q10 automatic regime routing.
Q11–14 choose EMA/ADX/RSI/MACD empirically; Q15 VWAP for entry/exit; Q16 all market structure; Q17 empirically choose breakout rules; Q18 sweeps optional; Q19 FVG+OB; Q20 candle patterns empirically.
Q21 volume empirically; Q22 order book depth+imbalance; Q23 CVD/delta empirically; Q24 OI+funding+liquidations; Q25 free sources only; Q26 5m; Q27 1m+5m; Q28 candle close only for selected strategies; Q29 probabilistic; Q30 early entry only under strict rules.
Q31 structure+ATR; Q32 dynamic target; Q33 empirical min R:R; Q34 1–2 candle validity; Q35 adaptive time stop; Q36 no quota; Q37 warn in research only; Q38 score+evidence; Q39 correlation-aware concurrent research candidates; Q40 all spread/vol/news vetoes.
Q41 maximum quality history; Q42 all metrics; Q43 multiple OOS/overfit protections; Q44 ML from start; Q45 compare decision mechanisms; Q46 Telegram entry/stop/target; Q47 separate research rejections; Q48 all metrics; Q49 strategy-specific thresholds; Q50 one hybrid engine.
