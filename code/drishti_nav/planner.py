"""Global A* on the risk-cost grid, arc-sampling local planner, confidence governor,
event manager and a unicycle controller."""
from __future__ import annotations

import time
import numpy as np
from skimage.graph import route_through_array

from .risk_map import RiskMap, LETHAL


# ------------------------------------------------------------------ governor
BANDS = [  # (name, min_conf, v_max, inflation_m, lambda, unknown_weight, local_forbid_risk)
    ("NORMAL",       0.75, 1.6, 0.5, 6.0, 1.0, 85.0),
    ("CAUTIOUS",     0.50, 1.0, 1.0, 9.0, 1.5, 76.0),
    ("CONSERVATIVE", 0.00, 0.5, 1.0, 14.0, 2.0, 66.0),   # in the dark, only clearly safe ground is driven
]


class Governor:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.c_ema = 0.9
        self.band = BANDS[0]

    def update(self, conf: float, loc_health: float):
        self.c_ema = 0.8 * self.c_ema + 0.2 * conf
        if not self.enabled:
            self.band = BANDS[0]
            return self.band, False
        prev = self.band
        target = BANDS[-1]
        for b in BANDS:
            if self.c_ema >= b[1]:
                target = b
                break
        # hysteresis: need +0.05 above a band's threshold to move up into it
        if prev[0] in [b[0] for b in BANDS] and BANDS.index(target) < BANDS.index(prev) and self.c_ema < target[1] + 0.05:
            target = prev
        self.band = target
        if loc_health < 0.2:
            self.band = ("RECOVER", 0.0, 0.25, 1.0, 14.0, 2.0, 66.0)
        return self.band, prev[0] != self.band[0]


# ------------------------------------------------------------- global planner
class GlobalPlanner:
    def __init__(self, rmap: RiskMap):
        self.rmap = rmap
        self.last_ms = 0.0

    def plan(self, start_xy, goal_xy, lam, inflation_m):
        t0 = time.perf_counter()
        res = self.rmap.res
        cost = self.rmap.cost_grid(lam, int(round(inflation_m / res)))
        s = (int(start_xy[1] / res), int(start_xy[0] / res))
        g = (int(goal_xy[1] / res), int(goal_xy[0] / res))
        cost[s] = 1.0
        cost[g] = min(cost[g], 1.0)
        cells, total = route_through_array(cost, s, g, fully_connected=True, geometric=True)
        self.last_ms = (time.perf_counter() - t0) * 1000
        cells = np.array(cells)
        xy = np.stack([(cells[:, 1] + 0.5) * res, (cells[:, 0] + 0.5) * res], 1)
        return cells, xy, float(total)


# -------------------------------------------------------------- local planner
class LocalPlanner:
    """Sample (v, w) arcs, roll out 2 s (vectorised), score by risk + path tracking + progress."""

    def __init__(self, rmap: RiskMap, dt=0.1, horizon=2.0):
        self.rmap = rmap
        self.dt, self.H = dt, horizon
        self.last_rollouts = []

    def plan(self, pose, path_xy, v_max, inflation_m, lam, forbid=85.0):
        from scipy.ndimage import maximum_filter
        x, y, th = pose
        res, n = self.rmap.res, self.rmap.n
        d = np.hypot(path_xy[:, 0] - x, path_xy[:, 1] - y)
        k = int(np.argmin(d))
        tgt = path_xy[min(k + 12, len(path_xy) - 1)]
        steps = int(self.H / self.dt)
        infl = int(round(inflation_m / res))
        lethal_map = maximum_filter(self.rmap.risk, size=2 * infl + 1) >= LETHAL if infl > 0 else self.rmap.risk >= LETHAL
        V, W = np.meshgrid(np.linspace(0.3 * v_max, v_max, 4), np.linspace(-1.2, 1.2, 13), indexing="ij")
        V, W = V.ravel(), W.ravel()
        A = len(V)
        px = np.full(A, x); py = np.full(A, y); pth = np.full(A, th)
        PX = np.zeros((A, steps)); PY = np.zeros((A, steps))
        for s_ in range(steps):
            px = px + V * np.cos(pth) * self.dt
            py = py + V * np.sin(pth) * self.dt
            pth = pth + W * self.dt
            PX[:, s_], PY[:, s_] = px, py
        I = (PY / res).astype(int); J = (PX / res).astype(int)
        inb = (I >= 0) & (I < n) & (J >= 0) & (J < n)
        Ic, Jc = np.clip(I, 0, n - 1), np.clip(J, 0, n - 1)
        raw_lethal = self.rmap.risk[Ic, Jc] >= forbid   # local planner never drives through near-lethal cells
        escape = np.arange(steps)[None, :] < 4          # first 0.4 s may leave an inflated zone
        lethal = (~inb) | raw_lethal | (lethal_map[Ic, Jc] & ~escape)
        feasible = ~lethal.any(1)
        risk_mean = self.rmap.risk[Ic, Jc].mean(1) / 100.0
        dist_tgt = np.hypot(tgt[0] - PX[:, -1], tgt[1] - PY[:, -1])
        score = lam * risk_mean * 3.0 + 1.0 * dist_tgt + 0.4 * np.abs(W) - 0.6 * V
        score[~feasible] = np.inf
        self.last_rollouts = [(list(zip(PX[a], PY[a])), score[a]) for a in range(A) if feasible[a]]
        if not feasible.any():
            return (0.0, 0.0), False
        b = int(np.argmin(score))
        return (float(V[b]), float(W[b])), True


# --------------------------------------------------------------- event logic
class EventManager:
    """Compares the risk along the upcoming path against the snapshot taken when that
    path was planned. Fires only on *changes*, never on hazards the planner already avoided."""

    def __init__(self):
        self.log = []
        self.last_global = -10.0
        self.snapshot = None
        self.blocked_since = None

    def emit(self, t, kind, detail=""):
        self.log.append((t, kind, detail))

    def take_snapshot(self, rmap: RiskMap, path_cells):
        self.snapshot = rmap.risk[path_cells[:, 0], path_cells[:, 1]].copy()

    def check(self, t, rmap: RiskMap, path_cells, pose_xy, band_changed, local_ok, lookahead=40):
        if self.snapshot is None or path_cells is None:
            return False
        res = rmap.res
        d = np.hypot((path_cells[:, 1] + 0.5) * res - pose_xy[0], (path_cells[:, 0] + 0.5) * res - pose_xy[1])
        k = int(np.argmin(d))
        seg = path_cells[k:k + lookahead]
        now = rmap.risk[seg[:, 0], seg[:, 1]]
        then = self.snapshot[k:k + lookahead]
        trigger = None
        if ((now >= LETHAL) & (then < LETHAL)).any():
            trigger = ("E1_path_blocked", f"new lethal cell on path (risk {now.max():.0f})")
        elif (now - then).mean() > 20:
            trigger = ("E2_path_risk_rise", f"mean +{(now - then).mean():.0f}")
        elif band_changed:
            trigger = ("E3_confidence_band_change", "cost function changed")
        elif not local_ok:
            # hold position first; escalate to a global replan only if blocked for > 2 s
            if self.blocked_since is None:
                self.blocked_since = t
                if not self.log or self.log[-1][1] != "HOLD_no_feasible_arc" or t - self.log[-1][0] > 3.0:
                    self.emit(t, "HOLD_no_feasible_arc", "vehicle holds, waiting for map to settle")
            elif t - self.blocked_since > 2.0:
                trigger = ("E4_blocked_2s", "global replan")
                self.blocked_since = None
        if local_ok:
            self.blocked_since = None
        if trigger and t - self.last_global > 0.5:
            self.last_global = t
            self.emit(t, *trigger)
            return True
        return False
