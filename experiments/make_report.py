"""Build results/summary.md and results/summary.json from the run folders: every table with
interquartile means and 95% bootstrap intervals, and a programmatic verdict on each hypothesis.

    python experiments/make_report.py
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np                                   # noqa: E402
from scipy.stats import mannwhitneyu                 # noqa: E402
from agrinegotiate.eval import stats                 # noqa: E402

RES = ROOT / "results"


def load(exp, label):
    f = RES / exp / label
    return stats.summarise(f) if list(f.glob("seed_*/metrics.json")) else None


def cell(s, k):
    if s is None or "iqm" not in s[k]:
        return "n/a"
    return f"{s[k]['iqm']:.3f} [{s[k]['ci95'][0]:.3f}, {s[k]['ci95'][1]:.3f}]"


def defined(s, k):
    return [v for v in s[k]["per_seed"] if v is not None]


def diff_ci(a, b, reps=5000, seed=0):
    """IQM(a) - IQM(b) with a 95% bootstrap interval (groups resampled independently)."""
    rng = np.random.default_rng(seed)
    a, b = np.asarray(a, float), np.asarray(b, float)

    def boot(x):
        samp = np.sort(rng.choice(x, size=(reps, x.size), replace=True), axis=1)
        cut = int(0.25 * x.size)
        return samp[:, cut:x.size - cut].mean(axis=1)
    d = boot(a) - boot(b)
    return stats.iqm(a) - stats.iqm(b), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def table(title, rows, cols=("E", "FGC", "S_F", "agreement_rate")):
    names = {"E": "Efficiency", "FGC": "Farmer gain capture", "S_F": "Farmer share", "agreement_rate": "Agreement",
             "lam_fair": "Fee rate", "fees_over_gstar": "Fees / G*", "price_share": "Price share"}
    out = [f"### {title}", "", "| Setting | Seeds | Failed | " + " | ".join(names[c] for c in cols) + " |",
           "| --- | --- | --- | " + " | ".join("---" for _ in cols) + " |"]
    for name, s in rows:
        if s is not None:
            out.append(f"| {name} | {s['n_seeds']} | {s['failed_runs']} | " + " | ".join(cell(s, c) for c in cols) + " |")
    return out + [""]


if __name__ == "__main__":
    L, V = ["# Results summary", "",
            "Interquartile mean over training seeds with a 95% bootstrap interval. Each seed's score is the mean of",
            "its last 10 evaluation checkpoints (300 fixed evaluation episodes each). A failed run ends with E below 0.1.",
            "Results with fewer than 10 seeds are exploratory.", ""], {}

    # gate
    gate = {k: load("x2_gate", k) for k in ("SYM", "PERISH", "DEADLINE", "INFO", "THIN3")}
    L += table("Unconstrained learners by scenario (X2)", gate.items())
    sym = gate["SYM"]
    if sym:
        e, sf = sym["E"], sym["S_F"]
        V["H1_efficiency"] = dict(passed=bool(e["ci95"][0] >= 0.85), detail=f"SYM E {cell(sym, 'E')}; needs the whole interval at or above 0.85")
        V["H1_fair_split"] = dict(passed=bool(sf["ci95"][0] >= 0.40 and sf["ci95"][1] <= 0.60),
                                  detail=f"SYM farmer share {cell(sym, 'S_F')}; per seed {[round(v, 2) for v in defined(sym, 'S_F')]}")
        for k in ("PERISH", "DEADLINE", "INFO", "THIN3"):
            g = gate[k]
            if g is None or not defined(g, "S_F"):
                continue
            a, b = defined(g, "S_F"), defined(sym, "S_F")
            d, lo, hi = diff_ci(a, b)
            p = mannwhitneyu(a, b, alternative="less").pvalue
            V[f"H2_{k}"] = dict(passed=bool(hi < 0), seeds=len(a),
                                detail=f"farmer share {k} minus SYM = {d:.3f} [{lo:.3f}, {hi:.3f}]; Mann-Whitney one-sided p = {p:.4f}; "
                                       f"{g['S_F']['undefined']} of {g['n_seeds']} {k} runs undefined")
    diag = [(k, load("x5_diagnosis", k)) for k in ("SYM_mix0", "SYMX")]
    L += table("SYM diagnosis (X5, exploratory)", diag)
    for k, s in diag:
        if s:
            L += [f"- {k} farmer share per seed: {[round(v, 2) for v in defined(s, 'S_F')]}"]
    L += [""]

    # mechanism
    base = gate["PERISH"]
    mech = sorted(p.name for p in (RES / "x3_mechanism").glob("*") if p.is_dir()) if (RES / "x3_mechanism").exists() else []
    rows = [("Unconstrained", base)] + [(m, load("x3_mechanism", m)) for m in mech]
    L += table("Mechanisms in PERISH (X3)", rows, ("E", "FGC", "S_F", "agreement_rate", "lam_fair", "fees_over_gstar"))
    fee = load("x3_mechanism", "fee_oracle_tau0.4")
    if fee and base:
        dF = diff_ci(fee["FGC"]["per_seed"], base["FGC"]["per_seed"])
        dE = diff_ci(fee["E"]["per_seed"], base["E"]["per_seed"])
        floors = [(m, load("x3_mechanism", m)) for m in mech if m.startswith("floor")]
        dom = [m for m, s in floors if s and s["FGC"]["iqm"] >= fee["FGC"]["iqm"] and s["E"]["iqm"] >= fee["E"]["iqm"]]
        V["H3_gain"] = dict(passed=bool(dF[1] >= 0.10), detail=f"FGC with fee minus without = {dF[0]:.3f} [{dF[1]:.3f}, {dF[2]:.3f}]; needs the whole interval at or above 0.10")
        V["H3_efficiency_cost"] = dict(passed=bool(dE[1] >= -0.05), detail=f"E with fee minus without = {dE[0]:.3f} [{dE[1]:.3f}, {dE[2]:.3f}]; needs the whole interval at or above -0.05")
        V["H3_beats_floor"] = dict(passed=bool(not dom), detail=("no price floor setting matches the fee on both E and FGC" if not dom else
                                   f"price floor settings that match or beat the fee on both E and FGC (point estimates): {dom}") + "; floors have 3 seeds each")

    het = sorted(q.name for q in (RES / "x6_hetero").glob("*") if q.is_dir()) if (RES / "x6_hetero").exists() else []
    L += table("Mechanisms when buyer values vary widely, PERISH-HET (X6, post hoc, exploratory)",
               [(m, load("x6_hetero", m)) for m in het], ("E", "FGC", "S_F", "agreement_rate", "lam_fair", "fees_over_gstar"))

    # scenarios calibrated on real mandi prices
    real = {k: load("x7_real", k) for k in ("unconstrained", "fee_oracle_tau0.4_eta0.25", "floor_kappa0.55", "unaware_duty0.6", "aware_duty0.6")}
    L += table("Scenarios calibrated on real Agmarknet lemon prices (X7)", real.items(), ("E", "FGC", "S_F", "agreement_rate", "lam_fair"))
    if real["unconstrained"] and real["fee_oracle_tau0.4_eta0.25"]:
        u, f = real["unconstrained"], real["fee_oracle_tau0.4_eta0.25"]
        dF, dE = diff_ci(f["FGC"]["per_seed"], u["FGC"]["per_seed"]), diff_ci(f["E"]["per_seed"], u["E"]["per_seed"])
        V["H3_real_gain"] = dict(passed=bool(dF[1] >= 0.10), detail=f"real-data PERISH-REAL: FGC with fee minus without = {dF[0]:.3f} [{dF[1]:.3f}, {dF[2]:.3f}]; needs the whole interval at or above 0.10")
        V["H3_real_efficiency_cost"] = dict(passed=bool(dE[1] >= -0.05), detail=f"real-data PERISH-REAL: E with fee minus without = {dE[0]:.3f} [{dE[1]:.3f}, {dE[2]:.3f}]; needs the whole interval at or above -0.05")
    if real["aware_duty0.6"] and real["unaware_duty0.6"]:
        d = diff_ci(real["aware_duty0.6"]["E"]["per_seed"], real["unaware_duty0.6"]["E"]["per_seed"])
        V["H5_real_delay_aware"] = dict(passed=bool(d[1] > 0), seeds=5, detail=f"real-data RURAL1-REAL-DTN: E delay-aware minus delay-unaware = {d[0]:.3f} [{d[1]:.3f}, {d[2]:.3f}]")

    # delay
    dl = {k: load("x4_delay", k) for k in ("unaware_duty1.0", "unaware_duty0.6", "unaware_duty0.4", "aware_duty1.0", "aware_duty0.6",
                                          "aware_duty0.4", "memory_only_duty0.6", "features_only_duty0.6")}
    L += table("Delay in RURAL1-DTN (X4, 3 seeds per cell, exploratory)", dl.items())
    u = [dl[f"unaware_duty{d}"] for d in ("1.0", "0.6", "0.4")]
    if all(u):
        es, ags = [s["E"]["iqm"] for s in u], [s["agreement_rate"]["iqm"] for s in u]
        V["H4_delay_cost"] = dict(passed=bool(es[0] > es[1] > es[2] and ags[0] > ags[1] > ags[2]), seeds=3,
                                  detail=f"delay-unaware E at link uptime 100/60/40%: {[round(v, 3) for v in es]}; agreement {[round(v, 3) for v in ags]}")
    if dl["aware_duty0.6"] and dl["unaware_duty0.6"]:
        d = diff_ci(dl["aware_duty0.6"]["E"]["per_seed"], dl["unaware_duty0.6"]["E"]["per_seed"])
        V["H5_delay_aware"] = dict(passed=bool(d[1] > 0), seeds=3, detail=f"E delay-aware minus delay-unaware at 60% uptime = {d[0]:.3f} [{d[1]:.3f}, {d[2]:.3f}]")

    L += ["## Hypothesis verdicts", "", "| Test | Result | Evidence |", "| --- | --- | --- |"]
    for k, v in V.items():
        tag = "PASS" if v["passed"] else "FAIL"
        if v.get("seeds", 10) < 10:
            tag += f" (exploratory, {v['seeds']} seeds)"
        L.append(f"| {k} | {tag} | {v['detail']} |")
    (RES / "summary.md").write_text("\n".join(L) + "\n")
    (RES / "summary.json").write_text(json.dumps(V, indent=1))
    print("\n".join(L))
