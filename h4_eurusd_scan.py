import sys, numpy as np
sys.path.insert(0, ".")
import h1_research as h
G = [g for g in h.GRID if g["family"] != "london"]
B = sys.argv[1] if len(sys.argv) > 1 else "data/forex/"
data = {s: h.load(f"{B}{s.lower()}/{s}_H4.csv") for s in ("EURUSD", "GBPUSD", "USDJPY")}
ind = {s: h.indicators(df) for s, df in data.items()}
def stats(xs):
    r = [x[1] for x in xs]
    return (len(r), round(float(np.mean(r)), 3) if r else None)
gross_cost = lambda s, p: {"half_spread": 0, "slip": 0, "fee": 0}
real_cost = h.costs
print("cfg | EURUSD train | EURUSD holdout | EURUSD holdout gross | GBPUSD holdout | USDJPY holdout")
for g in G:
    out = {}
    for s in data:
        t = h.simulate(s, data[s], ind[s], g)
        out[s] = ([x for x in t if x[0] < h.TRAIN_END], [x for x in t if x[0] >= h.TRAIN_END])
    h.costs = gross_cost; sw, sp = h.SWAP_PER_NIGHT, dict(h.SWAP_POINTS); h.SWAP_PER_NIGHT = 0; h.SWAP_POINTS.clear()
    tg = h.simulate("EURUSD", data["EURUSD"], ind["EURUSD"], g)
    h.costs = real_cost; h.SWAP_PER_NIGHT = sw; h.SWAP_POINTS.update(sp)
    print(h.name(g), "|", stats(out["EURUSD"][0]), "|", stats(out["EURUSD"][1]), "|",
          stats([x for x in tg if x[0] >= h.TRAIN_END]), "|", stats(out["GBPUSD"][1]), "|", stats(out["USDJPY"][1]))
