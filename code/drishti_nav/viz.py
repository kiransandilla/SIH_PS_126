"""Dashboard renderer: camera + segmentation/unknown overlay, risk map with paths,
confidence gauge, governor state, localization health and event log."""
from __future__ import annotations

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, ListedColormap
from matplotlib.patches import FancyBboxPatch

from .world import COLORS, CLASSES, NAME2ID
from .sensor import IMG_H

RISK_CMAP = LinearSegmentedColormap.from_list("risk", ["#1a9850", "#a6d96a", "#fee08b", "#f46d43", "#a50026"])
SEG_CMAP = ListedColormap(np.vstack([COLORS, [[0, 0, 0]]]))


def _gauge(ax, value, label, color):
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.02, 0.35), 0.96, 0.3, boxstyle="round,pad=0.01", fc="#e6e6e6", ec="none"))
    ax.add_patch(FancyBboxPatch((0.02, 0.35), 0.96 * max(value, 0.01), 0.3, boxstyle="round,pad=0.01", fc=color, ec="none"))
    ax.text(0.02, 0.8, label, fontsize=9, color="#333", va="center")
    ax.text(0.98, 0.8, f"{value:.2f}", fontsize=9, color="#333", va="center", ha="right", fontweight="bold")


def render_dashboard(sim, title="DRISHTI-Nav  ·  Adaptive Risk-Aware Visual Navigation (proof-of-concept)"):
    fig = plt.figure(figsize=(16, 9), dpi=100)
    fig.patch.set_facecolor("#f7f7f9")
    gs = fig.add_gridspec(12, 12, left=0.03, right=0.98, top=0.93, bottom=0.03, hspace=0.9, wspace=0.6)
    fig.text(0.03, 0.965, title, fontsize=15, fontweight="bold", color="#1e2761")
    fig.text(0.98, 0.965, f"t = {sim.t:5.1f} s", fontsize=12, ha="right", color="#333")

    # camera
    ax = fig.add_subplot(gs[0:5, 0:5]); ax.imshow(sim.frame); ax.set_title("Simulated camera feed", fontsize=10, loc="left"); ax.axis("off")
    # segmentation + unknown overlay
    ax = fig.add_subplot(gs[5:10, 0:5])
    p = sim.last_percep
    seg = COLORS[np.clip(p["pred"], 0, len(CLASSES) - 1)].copy()
    seg[~p["valid"]] = sim.frame[~p["valid"]]
    over = 0.25 * sim.frame + 0.75 * seg
    unk = p["unknown"] > 0.55
    over[unk] = [0.85, 0.2, 0.9]
    ax.imshow(over); ax.axis("off")
    ax.set_title("Perception: terrain classes  ·  magenta = UNKNOWN (energy score)", fontsize=10, loc="left")
    # legend
    for k, (name, risk, col) in enumerate(CLASSES):
        ax.add_patch(plt.Rectangle((4 + k * 40, IMG_H - 14), 10, 10, color=np.array(col) / 255))
        ax.text(16 + k * 40, IMG_H - 6, f"{name} {risk}", fontsize=6.5, color="white",
                bbox=dict(fc="black", alpha=0.35, pad=1, ec="none"))

    # risk map
    ax = fig.add_subplot(gs[0:10, 5:12])
    w = sim.world
    r = sim.rmap.risk.copy()
    ax.imshow(r, cmap=RISK_CMAP, vmin=0, vmax=100, origin="lower", extent=[0, w.size_m, 0, w.size_m], interpolation="nearest")
    unseen = ~sim.rmap.seen
    ax.imshow(np.where(unseen, 1.0, np.nan), cmap=ListedColormap(["#c9c9c9"]), origin="lower",
              extent=[0, w.size_m, 0, w.size_m], alpha=0.85, interpolation="nearest")
    unk_cells = (sim.rmap.unknown > 0.45) & sim.rmap.seen
    if unk_cells.any():
        ax.imshow(np.where(unk_cells, 1.0, np.nan), cmap=ListedColormap(["#d633e0"]), origin="lower",
                  extent=[0, w.size_m, 0, w.size_m], alpha=0.9, interpolation="nearest")
    if sim.alt_xy is not None:
        ax.plot(sim.alt_xy[:, 0], sim.alt_xy[:, 1], color="#888", lw=1.4, ls="--", label="shortest-distance route")
    if sim.path_xy is not None:
        ax.plot(sim.path_xy[:, 0], sim.path_xy[:, 1], color="white", lw=2.4, label="risk-aware global path")
    for pts, sc in sim.lplan.last_rollouts[::6]:
        if len(pts) > 1:
            pts = np.array(pts); ax.plot(pts[:, 0], pts[:, 1], color="#00e5ff", lw=0.5, alpha=0.5)
    tt = np.array(sim.traj_true); te = np.array(sim.traj_est)
    ax.plot(tt[:, 0], tt[:, 1], color="black", lw=1.2, ls=":", label="ground-truth trajectory")
    ax.plot(te[:, 0], te[:, 1], color="#1e90ff", lw=1.6, label="visual-odometry estimate")
    x, y, th = sim.pose
    ax.plot(x, y, marker=(3, 0, np.degrees(th) - 90), ms=14, color="#ffd400", mec="black")
    ax.plot(*w.start, "s", ms=9, color="#00c853", mec="black"); ax.text(w.start[0] + 1.5, w.start[1] - 2, "A", fontsize=12, fontweight="bold")
    ax.plot(*w.goal, "*", ms=15, color="#ff1744", mec="black"); ax.text(w.goal[0] + 1.5, w.goal[1] - 2, "B", fontsize=12, fontweight="bold")
    # FOV wedge
    from .sensor import HFOV, RANGE
    a = np.linspace(th - HFOV / 2, th + HFOV / 2, 20)
    ax.fill(np.r_[x, x + RANGE * np.cos(a)], np.r_[y, y + RANGE * np.sin(a)], color="yellow", alpha=0.12)
    ax.set_title("Dynamic risk map (0 = safe · 100 = lethal · grey = unobserved · magenta = unknown)", fontsize=10, loc="left")
    ax.set_xlim(0, w.size_m); ax.set_ylim(0, w.size_m); ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)")
    ax.legend(loc="lower right", fontsize=7.5, framealpha=0.9)

    # gauges
    band = sim.gov.band
    c = sim.gov.c_ema
    col = "#2e7d32" if c >= 0.75 else ("#f9a825" if c >= 0.5 else "#c62828")
    _gauge(fig.add_subplot(gs[10, 0:3]), c, "Perception confidence", col)
    _gauge(fig.add_subplot(gs[10, 3:6]), sim.vo.health, f"Localization health ({sim.vo.features} features)", "#1565c0")
    ax = fig.add_subplot(gs[10, 6:12]); ax.axis("off")
    ax.text(0, 0.7, f"Governor band: {band[0]}", fontsize=11, fontweight="bold",
            color={"NORMAL": "#2e7d32", "CAUTIOUS": "#f9a825", "CONSERVATIVE": "#c62828", "RECOVER": "#6a1b9a"}.get(band[0], "#333"))
    ax.text(0, 0.15, f"v_max {band[2]:.1f} m/s · cmd {sim.v_cmd:.2f} m/s · margin {band[3]:.1f} m · risk weight λ={band[4]:.0f} · "
                     f"sun {sim.world.sun:.2f} · replans {len(sim.replan_ms)}", fontsize=9, color="#333")
    # event log
    ax = fig.add_subplot(gs[11, 0:12]); ax.axis("off")
    lines = [f"[{t:6.1f}s] {k}  {d}"[:70] for t, k, d in sim.events.log[-3:]]
    ax.text(0, 0.9, "EVENT LOG   " + "   |   ".join(lines), fontsize=8.5, family="monospace", va="top", color="#222")
    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba())[..., :3].copy()
    plt.close(fig)
    return buf
