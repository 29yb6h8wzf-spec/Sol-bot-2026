# Task 3 — cost sensitivity (offline calculation, NOT a backtest)

Inputs: $37.50 allocation/market; 2x max ($75 notional); $0.375 max risk;
0.05% taker per side; 0.03%–0.05% slippage per side. Costs are
0.16%–0.20% of notional round-trip. Price and step filters from Task 2
dated Binance public snapshot, not an execution quote.

Position sizing is min($0.375 / (price * (stop_fraction + round_trip_cost_fraction)),
$75 / price), rounded DOWN to step. All-in stop-loss budget includes fees and
slippage, unlike the earlier stop-only Task 2 analysis.

| Symbol | Stop | Qty at 0.03% slip/side | All-in cost USD (% of $0.375) | Qty at 0.05% slip/side | All-in cost USD (% of $0.375) |
|---|---:|---:|---:|---:|---:|
| ETH | 0.3% | 0.033 | 0.1182 (31.51%) | 0.033 | 0.1477 (39.39%) |
| ETH | 0.5% | 0.025 | 0.0895 (23.87%) | 0.023 | 0.1029 (27.45%) |
| ETH | 1.0% | 0.014 | 0.0501 (13.37%) | 0.013 | 0.0582 (15.52%) |
| ETH | 2.0% | 0.007 | 0.0251 (6.68%) | 0.007 | 0.0313 (8.36%) |
| SOL | 0.3% | 0.83 | 0.1189 (31.71%) | 0.83 | 0.1486 (39.63%) |
| SOL | 0.5% | 0.63 | 0.0902 (24.07%) | 0.59 | 0.1056 (28.17%) |
| SOL | 1.0% | 0.36 | 0.0516 (13.75%) | 0.34 | 0.0609 (16.23%) |
| SOL | 2.0% | 0.19 | 0.0272 (7.26%) | 0.19 | 0.0340 (9.07%) |
| XRP | 0.3% | 64.4 | 0.1198 (31.95%) | 64.4 | 0.1498 (39.94%) |
| XRP | 0.5% | 48.8 | 0.0908 (24.21%) | 46.0 | 0.1070 (28.53%) |
| XRP | 1.0% | 27.8 | 0.0517 (13.79%) | 26.8 | 0.0623 (16.62%) |
| XRP | 2.0% | 14.9 | 0.0277 (7.39%) | 14.6 | 0.0340 (9.05%) |

The ETH 2% rows are NOT TRADABLE: notionals $15.6659 below Binance $20 minimum.

Minimum stop distance where **total fees + slippage** < $0.05625 (15% of risk),
based on 0.000001 stop-fraction grid and exchange quantity step:

| Symbol | 0.03% slippage/side | 0.05% slippage/side |
|---|---:|---:|
| ETH | 0.8873% | 1.0890% |
| SOL | 0.8872% | 1.1090% |
| XRP | 0.9044% | 1.1327% |

Minimum stop distance for **taker fees alone** < $0.05625,
using the same fee+slippage-inclusive position sizing:

| Symbol | 0.03% slippage/side | 0.05% slippage/side |
|---|---:|---:|
| ETH | 0.4845% | 0.4445% |
| SOL | 0.5049% | 0.4649% |
| XRP | 0.5064% | 0.4664% |

The precise minimum depends on price, quantity steps, minimum notional,
and fee/slippage assumptions; it is not a stable trading parameter.

**Median backtest holding time: unavailable.** No authenticated historical
backtest was executed in this task. The new max-holding exit is evaluated only
on completed 15m bars, so 5-minute exits are not possible at this resolution.

No claim of profitability or live-trading readiness.
