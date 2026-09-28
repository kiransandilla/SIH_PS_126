"""Outdoor terrain world for the DRISHTI-Nav proof-of-concept simulator.

Grid world (metres) with terrain classes, discrete obstacles, a ditch, and a
directional sun. Ground truth only; the robot never reads this directly.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

# Terrain / object classes (index -> name, risk, RGB colour used by the renderer)
CLASSES = [
    ("grass",   10, (92, 150, 62)),
    ("dirt",    22, (150, 112, 70)),
    ("gravel",  38, (140, 138, 128)),
    ("mud",     78, (84, 60, 36)),
    ("rock",    97, (110, 105, 100)),
    ("tree",    99, (40, 78, 34)),
    ("ditch",  100, (30, 28, 30)),
    ("novel",   60, (190, 60, 200)),   # never seen in training -> unknown
]
NAME2ID = {c[0]: i for i, c in enumerate(CLASSES)}
RISK_TABLE = np.array([c[1] for c in CLASSES], dtype=np.float32)
COLORS = np.array([c[2] for c in CLASSES], dtype=np.float32) / 255.0
OBSTACLE_IDS = {NAME2ID["rock"], NAME2ID["tree"], NAME2ID["ditch"], NAME2ID["novel"]}
# Height of standing objects (m) used by the perspective renderer
HEIGHT = {NAME2ID["rock"]: 0.5, NAME2ID["tree"]: 3.0, NAME2ID["novel"]: 0.8}


class World:
    def __init__(self, size_m: float = 80.0, res: float = 0.5, seed: int = 0):
        self.res = res
        self.n = int(size_m / res)
        self.size_m = size_m
        self.rng = np.random.default_rng(seed)
        self.terrain = np.zeros((self.n, self.n), dtype=np.int16)
        self.sun = 1.0          # 0..1 intensity
        self.sun_azimuth = 0.8  # radians, for shadow direction
        self.start = np.array([6.0, 6.0])
        self.goal = np.array([size_m - 8.0, size_m - 8.0])
        self._build()

    # ------------------------------------------------------------------ build
    def _noise(self, sigma):
        return gaussian_filter(self.rng.standard_normal((self.n, self.n)), sigma)

    def _disc(self, cx, cy, r):
        yy, xx = np.mgrid[0:self.n, 0:self.n]
        return (xx * self.res - cx) ** 2 + (yy * self.res - cy) ** 2 <= r ** 2

    def _build(self):
        n1 = self._noise(6)
        n2 = self._noise(3)
        t = np.full((self.n, self.n), NAME2ID["grass"], dtype=np.int16)
        t[n1 > 0.35] = NAME2ID["dirt"]
        t[(n1 > 0.15) & (n2 > 0.5)] = NAME2ID["gravel"]
        # A mud belt across the direct diagonal, so the shortest path is the risky one
        yy, xx = np.mgrid[0:self.n, 0:self.n]
        x = xx * self.res
        y = yy * self.res
        d = np.abs((y - x)) / np.sqrt(2)           # distance to the A->B diagonal
        along = (x + y) / 2
        mud = (d < 6.0) & (along > 26) & (along < 44) & (n2 > -0.6)
        t[mud] = NAME2ID["mud"]
        # gravel around the mud belt
        t[(d < 9) & (d >= 6) & (along > 24) & (along < 46) & (n2 > -0.2)] = NAME2ID["gravel"]
        # ditch: a narrow channel on the upper-left side
        ditch = (np.abs(y - 0.55 * x - 30) < 1.0) & (x > 8) & (x < 40)
        t[ditch] = NAME2ID["ditch"]
        # tree line on the lower-right side
        for cx in np.arange(30, 74, 3.2):
            cy = 0.62 * cx - 12 + self.rng.normal(0, 1.2)
            if 0 < cy < self.size_m:
                t[self._disc(cx, cy, 1.1)] = NAME2ID["tree"]
        # scattered rocks
        for _ in range(28):
            cx, cy = self.rng.uniform(4, self.size_m - 4, 2)
            if np.hypot(*(np.array([cx, cy]) - self.start)) < 6 or np.hypot(*(np.array([cx, cy]) - self.goal)) < 6:
                continue
            t[self._disc(cx, cy, self.rng.uniform(0.6, 1.3))] = NAME2ID["rock"]
        self.terrain = t
        self.base_terrain = t.copy()

    # --------------------------------------------------------------- dynamics
    def spawn(self, cls: str, cx: float, cy: float, r: float = 1.0):
        self.terrain[self._disc(cx, cy, r)] = NAME2ID[cls]

    def set_sun(self, intensity: float):
        self.sun = float(np.clip(intensity, 0.05, 1.0))

    def cell(self, x: float, y: float) -> int:
        i = int(np.clip(y / self.res, 0, self.n - 1))
        j = int(np.clip(x / self.res, 0, self.n - 1))
        return int(self.terrain[i, j])

    def is_obstacle(self, x: float, y: float) -> bool:
        return self.cell(x, y) in OBSTACLE_IDS

    def in_bounds(self, x, y):
        return 0 <= x < self.size_m and 0 <= y < self.size_m
