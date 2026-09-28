"""Visual-odometry stand-in: integrates motion with drift that grows when the camera
sees few trackable features (open grass / sky), fused with wheel odometry.
Reports a tracking-health signal like a real VO front-end would."""
from __future__ import annotations

import numpy as np
from .world import HEIGHT


class VisualOdometry:
    def __init__(self, pose0, rng: np.random.Generator):
        self.est = np.array(pose0, dtype=float)
        self.rng = rng
        self.health = 1.0
        self.features = 300

    def step(self, true_pose, prev_true, observed_cells, dt):
        # feature count ~ textured objects in view + terrain texture
        n_obj = sum(1 for (c, r) in observed_cells.values() if c in HEIGHT)
        n_tex = sum(1 for (c, r) in observed_cells.values() if c in (1, 2, 4))
        self.features = int(60 + 6 * n_obj + 0.3 * n_tex + self.rng.normal(0, 8))
        raw = float(np.clip((self.features - 30) / 120, 0, 1))
        self.health = 0.85 * self.health + 0.15 * raw
        # integrate true delta with drift inversely proportional to health; wheel odom fusion caps it
        d = np.array(true_pose) - np.array(prev_true)
        sigma = 0.008 + 0.04 * (1 - self.health)
        noise = self.rng.normal(0, sigma, 3) * np.array([1, 1, 0.3]) * np.linalg.norm(d[:2]) * 5
        self.est = self.est + d + noise
        return self.est.copy()
