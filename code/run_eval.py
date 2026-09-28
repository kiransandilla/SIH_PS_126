"""Seeded evaluation: baseline (binary obstacle map, shortest path, constant speed) vs
risk-aware without governor vs full DRISHTI-Nav. Writes results.csv and summary.md."""
import argparse, csv, os
import numpy as np
from drishti_nav.sim import Simulator
from run_demo import SCENARIO


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", type=int, default=20); ap.add_argument("--out", default="output")
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    rows = []
    for mode in ["baseline", "risk_only", "full"]:
        for seed in range(a.runs):
            sim = Simulator(seed=100 + seed, mode=mode, scenario=SCENARIO, headless=True)
            m = sim.run(); m["seed"] = seed; rows.append(m)
            print(mode, seed, m)
    keys = list(rows[0].keys())
    with open(os.path.join(a.out, "results.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    lines = ["| Metric | Baseline (binary + shortest) | Risk-aware (no governor) | DRISHTI-Nav (full) |", "|---|---|---|---|"]
    def col(mode, fn):
        return fn([r for r in rows if r["mode"] == mode])
    metrics = [
        ("Success rate (no collision, reached B)", lambda rs: f"{100*np.mean([r['success'] for r in rs]):.0f} %"),
        ("Runs with a collision", lambda rs: f"{sum(r['collided'] for r in rs)} / {len(rs)}"),
        ("Mud steps traversed (mean)", lambda rs: f"{np.mean([r['mud_steps'] for r in rs]):.0f}"),
        ("Path length (m, mean)", lambda rs: f"{np.mean([r['path_len'] for r in rs]):.1f}"),
        ("Time to goal (s, mean)", lambda rs: f"{np.mean([r['time_s'] for r in rs]):.0f}"),
        ("Global replans per run", lambda rs: f"{np.mean([r['replans'] for r in rs]):.1f}"),
        ("Replan latency (ms, mean)", lambda rs: f"{np.mean([r['replan_ms'] for r in rs if r['replans']]) if any(r['replans'] for r in rs) else 0:.0f}"),
        ("Hazard detection latency (ms)", lambda rs: f"{np.mean([r['detect_ms'] for r in rs if r['detect_ms'] is not None]) if any(r['detect_ms'] is not None for r in rs) else float('nan'):.0f}"),
        ("Localization ATE (m, mean)", lambda rs: f"{np.mean([r['ate_m'] for r in rs]):.2f}"),
    ]
    for name, fn in metrics:
        lines.append(f"| {name} | {col('baseline', fn)} | {col('risk_only', fn)} | {col('full', fn)} |")
    md = "\n".join(lines)
    open(os.path.join(a.out, "summary.md"), "w").write(md + "\n")
    print("\n" + md)


if __name__ == "__main__":
    main()
