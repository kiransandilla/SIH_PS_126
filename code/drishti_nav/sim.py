"""Closed-loop simulation: camera -> perception -> localization -> risk map ->
events -> planner -> governor -> controller -> vehicle -> next frame."""
from __future__ import annotations

import numpy as np

from .world import World, NAME2ID, OBSTACLE_IDS, CLASSES
from .sensor import Camera, PerceptionStub, IMG_H, IMG_W
from .risk_map import RiskMap
from .planner import GlobalPlanner, LocalPlanner, Governor, EventManager
from .localization import VisualOdometry

K = len(CLASSES)


class Simulator:
    def __init__(self, seed=0, mode="full", scenario=None, dt=0.1, headless=False):
        self.headless = headless
        """mode: 'full' (risk-aware + governor), 'risk_only' (no governor), 'baseline' (binary)."""
        self.rng = np.random.default_rng(seed)
        self.world = World(seed=seed)
        self.cam = Camera(self.world) if not headless else Camera(self.world, 45, 80)
        self.percep = PerceptionStub(self.rng)
        self.rmap = RiskMap(self.world.n, self.world.res)
        self.mode = mode
        self.rmap.binary_mode = (mode == "baseline")
        if self.rmap.binary_mode:
            self.rmap.risk[:] = 0.0
        self.gov = Governor(enabled=(mode == "full"))
        self.gplan = GlobalPlanner(self.rmap)
        self.lplan = LocalPlanner(self.rmap, dt=dt)
        self.events = EventManager()
        self.dt = dt
        self.t = 0.0
        th0 = np.arctan2(*(self.world.goal - self.world.start)[::-1])
        self.pose = np.array([*self.world.start, th0])
        self.vo = VisualOdometry(self.pose, self.rng)
        self.est = self.pose.copy()
        self.scenario = list(scenario or [])
        self.fired = []
        self.traj_true, self.traj_est = [self.pose[:2].copy()], [self.est[:2].copy()]
        self.path_cells, self.path_xy = None, None
        self.alt_xy = None
        self.done, self.collided, self.collisions = False, False, 0
        self.hazard_cells = 0
        self.path_len = 0.0
        self.risk_trace = []
        self.replan_ms = []
        self.detect_latency = []
        self.pending_detect = None
        self.frame = None
        self.last_percep = None
        self.v_cmd = 0.0
        self.max_t = 260.0
        self._initial_plan()

    # ------------------------------------------------------------- planning
    def _initial_plan(self):
        band = self.gov.band
        self.path_cells, self.path_xy, _ = self.gplan.plan(self.est[:2], self.world.goal, band[4], band[3])
        # alternative: pure shortest path (what a distance-only planner would do)
        self.alt_cells, self.alt_xy, _ = self.gplan.plan(self.est[:2], self.world.goal, 0.0, 0.5)
        self.events.take_snapshot(self.rmap, self.path_cells)
        self.events.emit(0.0, "PLAN_initial", f"A*: {self.gplan.last_ms:.0f} ms")

    def _replan(self):
        band = self.gov.band
        self.path_cells, self.path_xy, _ = self.gplan.plan(self.est[:2], self.world.goal, band[4], band[3])
        self.replan_ms.append(self.gplan.last_ms)
        self.events.take_snapshot(self.rmap, self.path_cells)
        self.events.log[-1] = (self.events.log[-1][0], self.events.log[-1][1],
                               self.events.log[-1][2] + f" -> replan {self.gplan.last_ms:.0f} ms")

    # ------------------------------------------------------------ scenario
    def _fire_events(self):
        for ev in self.scenario:
            if ev in self.fired:
                continue
            if self.t < ev.get("t", 0):
                continue
            self.fired.append(ev)
            if ev["type"] == "spawn":
                # place on the current path `dist` metres ahead of the robot
                d = np.hypot(self.path_xy[:, 0] - self.pose[0], self.path_xy[:, 1] - self.pose[1])
                k = int(np.argmin(d))
                cum = np.cumsum(np.r_[0, np.hypot(*np.diff(self.path_xy[k:], axis=0).T)])
                m = k + int(np.searchsorted(cum, ev.get("dist", 7.0)))
                m = min(m, len(self.path_xy) - 1)
                cx, cy = self.path_xy[m]
                self.world.spawn(ev["cls"], cx, cy, ev.get("r", 1.0))
                self.events.emit(self.t, "WORLD_" + ev["cls"] + "_appears", f"at ({cx:.0f},{cy:.0f}) m")
                sh = np.round((self.est[:2] - self.pose[:2]) / self.world.res).astype(int)
                self.pending_detect = (self.t, int(cy / self.world.res) + sh[1], int(cx / self.world.res) + sh[0])
            elif ev["type"] == "sun":
                self.world.set_sun(ev["value"])
                self.events.emit(self.t, "WORLD_lighting", f"sun intensity -> {ev['value']:.2f}")

    # ----------------------------------------------------------------- step
    def step(self):
        if self.done:
            return
        self._fire_events()
        w = self.world
        # 1. sense
        cells = self.cam.observed_cells(self.pose)
        img, lab = self.cam.render(self.pose, self.rng, cells)
        # 2. perceive (image-space result only needed for the dashboard)
        feats = self.cam.image_features(img)
        quality = float(np.clip(2.0 * feats["mean_lum"] + 2.0 * feats["contrast"] - 1.2 * feats["dark_frac"], 0.25, 1.0))
        if not self.headless:
            p = self.percep.infer(img, lab)
            self.frame, self.last_percep = img, p
        # the map lives in the odometry (estimated) frame, exactly as on a real robot:
        # observations are projected with the *estimated* pose, so drift shows up as map smear
        shift = np.round((self.est[:2] - self.pose[:2]) / w.res).astype(int)[::-1]
        keys = np.clip(np.array(list(cells.keys())).reshape(-1, 2) + shift, 0, w.n - 1)
        vals = list(cells.values())
        cls = np.array([v[0] for v in vals], dtype=int)
        rr = np.array([v[1] for v in vals], dtype=float)
        M = len(cls)
        temp = 0.4 + 1.2 * (1 - quality)
        logits = np.full((M, K), -3.0)
        logits[np.arange(M), cls] += 8.0 * quality * (1.0 - 0.3 * rr / 14.0)
        novel = cls == NAME2ID["novel"]
        logits[novel] = self.rng.normal(-4.0, 0.8, (int(novel.sum()), K))   # no known class explains it
        logits[:, NAME2ID["novel"]] = -8.0
        logits += self.rng.normal(0, temp, (M, K))
        pr = np.exp(logits - logits.max(1, keepdims=True)); pr /= pr.sum(1, keepdims=True)
        energy = -np.log(np.exp(logits).sum(1))
        unk = np.clip((energy - 0.2) / 1.6, 0, 1)
        conf = float(np.clip(0.35 * pr.max(1).mean() + 0.45 * quality + 0.20 * (1 - feats["shadow_ratio"]), 0, 1))
        if not self.headless:
            self.last_percep["conf"] = conf
        if self.mode != "full":
            conf = 1.0
        if self.mode == "baseline":
            unk[:] = 0.0                                   # baseline: 'not detected -> safe'
            hard = np.zeros_like(pr); hard[np.arange(M), pr.argmax(1)] = 1.0; pr = hard
        # 3. localize
        prev = self.pose.copy()
        # 4. map
        self.rmap.unknown_weight = self.gov.band[5]
        self.rmap.update(keys[:, 0], keys[:, 1], pr.astype(np.float32), unk.astype(np.float32), conf, self.t)
        if self.pending_detect and self.rmap.risk[self.pending_detect[1], self.pending_detect[2]] >= 60:
            self.detect_latency.append(self.t - self.pending_detect[0] + self.dt)
            self.events.emit(self.t, "DETECT_new_hazard", f"latency {self.detect_latency[-1]*1000:.0f} ms")
            self.pending_detect = None
        # 5. govern + events
        band, changed = self.gov.update(conf, self.vo.health if self.mode == "full" else 1.0)
        if changed:
            self.events.emit(self.t, "GOV_band", f"{band[0]} (C={self.gov.c_ema:.2f})")
        (v, wz), ok = self.lplan.plan(self.est, self.path_xy, band[2], band[3], band[4], band[6])
        if self.events.check(self.t, self.rmap, self.path_cells, self.est[:2], changed, ok):
            self._replan()
            (v, wz), ok = self.lplan.plan(self.est, self.path_xy, band[2], band[3], band[4], band[6])
        if not ok:
            v, wz = 0.0, 0.6      # rotate in place to search
        # 6. move (mud slows the real vehicle)
        slip = 0.45 if w.cell(*self.pose[:2]) == NAME2ID["mud"] else 1.0
        self.v_cmd = v
        self.pose[0] += v * slip * np.cos(self.pose[2]) * self.dt
        self.pose[1] += v * slip * np.sin(self.pose[2]) * self.dt
        self.pose[2] += wz * self.dt
        self.est = self.vo.step(self.pose, prev, cells, self.dt)
        self.path_len += float(np.hypot(*(self.pose[:2] - prev[:2])))
        self.traj_true.append(self.pose[:2].copy()); self.traj_est.append(self.est[:2].copy())
        c = w.cell(*self.pose[:2])
        if c in OBSTACLE_IDS:
            self.collisions += 1
            if not self.collided:
                self.events.emit(self.t, "COLLISION", CLASSES[c][0])
            self.collided = True
        if c == NAME2ID["mud"]:
            self.hazard_cells += 1
        self.t += self.dt
        if np.hypot(*(self.pose[:2] - w.goal)) < 1.5:
            self.done = True
            self.events.emit(self.t, "GOAL_reached", f"{self.path_len:.1f} m in {self.t:.0f} s")
        elif self.t > self.max_t:
            self.done = True
            self.events.emit(self.t, "TIMEOUT", "")

    def run(self, max_steps=3000):
        while not self.done and max_steps > 0:
            self.step(); max_steps -= 1
        return self.metrics()

    def metrics(self):
        ate = float(np.mean([np.hypot(*(a - b)) for a, b in zip(self.traj_true, self.traj_est)]))
        return dict(mode=self.mode, success=bool(self.done and not self.collided and self.t <= self.max_t),
                    collided=self.collided, collision_steps=self.collisions,
                    mud_steps=self.hazard_cells, path_len=round(self.path_len, 1), time_s=round(self.t, 1),
                    replans=len(self.replan_ms), replan_ms=round(float(np.mean(self.replan_ms)), 1) if self.replan_ms else 0.0,
                    detect_ms=round(1000 * float(np.mean(self.detect_latency)), 0) if self.detect_latency else None,
                    ate_m=round(ate, 2))
