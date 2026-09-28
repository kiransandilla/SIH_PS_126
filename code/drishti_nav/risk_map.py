"""Multi-layer dynamic risk map with temporal fusion and corridor change detection."""
from __future__ import annotations

import numpy as np

from .world import RISK_TABLE, NAME2ID, CLASSES, OBSTACLE_IDS

K = len(CLASSES)
UNSEEN_RISK = 35.0        # prior for never-observed cells (uncertain)
LETHAL = 90.0


class RiskMap:
    def __init__(self, n: int, res: float):
        self.n, self.res = n, res
        self.cls = np.full((n, n, K), 1.0 / K, dtype=np.float32)   # class belief (EMA)
        self.obs_lo = np.zeros((n, n), dtype=np.float32)            # obstacle log-odds
        self.unknown = np.zeros((n, n), dtype=np.float32)
        self.conf = np.zeros((n, n), dtype=np.float32)
        self.seen = np.zeros((n, n), dtype=bool)
        self.last_seen = np.full((n, n), -1e9, dtype=np.float32)
        self.risk = np.full((n, n), UNSEEN_RISK, dtype=np.float32)
        self.binary_mode = False     # baseline: obstacle-only, no terrain risk
        self.unknown_weight = 1.0

    def update(self, ii, jj, probs, unk, conf: float, t: float):
        """Fuse one frame of observations: cell indices, class probabilities (M,K), unknown scores (M,)."""
        if len(ii) == 0:
            return
        a = 0.35 + 0.4 * conf                       # trust the update more when confident
        self.cls[ii, jj] = (1 - a) * self.cls[ii, jj] + a * probs
        p_obs = probs[:, list(OBSTACLE_IDS)].sum(1)
        lo = np.log(np.clip(p_obs, 0.02, 0.98) / np.clip(1 - p_obs, 0.02, 0.98))
        # evidence accumulates over consistent frames; a single noisy frame cannot create a lethal cell
        self.obs_lo[ii, jj] = np.clip(self.obs_lo[ii, jj] * 0.85 + lo * (0.1 + 0.5 * conf ** 2), -6, 6)
        self.unknown[ii, jj] = 0.6 * self.unknown[ii, jj] + 0.4 * unk
        self.conf[ii, jj] = 0.7 * self.conf[ii, jj] + 0.3 * conf
        self.seen[ii, jj] = True
        self.last_seen[ii, jj] = t
        self._recompute(ii, jj)

    def _recompute(self, ii, jj):
        p = self.cls[ii, jj]
        if self.binary_mode:
            p_obs = 1 / (1 + np.exp(-self.obs_lo[ii, jj]))
            r = np.where(p_obs > 0.5, 100.0, 0.0)
        else:
            r_terrain = p @ RISK_TABLE
            p_obs = 1 / (1 + np.exp(-self.obs_lo[ii, jj]))
            r_obs = 100.0 * p_obs
            u = np.clip(self.unknown[ii, jj] * self.unknown_weight, 0, 1)
            r_unk = np.where(u > 0.25, 60.0 + 50.0 * u, 0.0)   # sustained unknown -> lethal
            r = np.maximum(np.maximum(r_terrain, r_obs), r_unk)
            # low observation confidence pulls risk toward the uncertain prior
            c = self.conf[ii, jj]
            r = c * r + (1 - c) * np.maximum(r, 45.0)
        self.risk[ii, jj] = np.clip(r, 0, 100)

    def decay(self, t: float, tau: float = 25.0):
        """Cells not re-observed drift back toward the uncertain prior (dynamic forgetting)."""
        stale = self.seen & (t - self.last_seen > 4.0)
        if stale.any():
            self.obs_lo[stale] *= 0.985
            self.unknown[stale] *= 0.99
            ii, jj = np.nonzero(stale)
            self._recompute(ii, jj)

    # ---------------------------------------------------------- planner cost
    def cost_grid(self, lam: float, inflate_cells: int) -> np.ndarray:
        r = self.risk / 100.0
        cost = 1.0 + lam * r ** 2
        lethal = self.risk >= LETHAL
        if inflate_cells > 0:
            from scipy.ndimage import binary_dilation
            lethal = binary_dilation(lethal, iterations=inflate_cells)
        cost[lethal] = 1e6
        return cost

    def corridor_risk(self, path_cells, width: int = 2):
        """Max risk within `width` cells of the path."""
        if path_cells is None or len(path_cells) == 0:
            return 0.0
        best = 0.0
        for (i, j) in path_cells:
            i0, i1 = max(i - width, 0), min(i + width + 1, self.n)
            j0, j1 = max(j - width, 0), min(j + width + 1, self.n)
            best = max(best, float(self.risk[i0:i1, j0:j1].max()))
        return best
