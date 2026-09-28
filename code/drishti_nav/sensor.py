"""Simulated forward camera: perspective render of the terrain grid + perception stub.

The renderer is a pinhole camera at height H with pitch P looking along the
robot heading. Ground pixels are back-projected to the terrain grid; standing
objects (rocks, trees, novel objects) are drawn as vertical billboards. Lighting
(sun intensity, cast shadows, sensor noise) affects the image, and the
perception stub's noise is driven by the *rendered image statistics*, so the
confidence estimator operates on real image features.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

from .world import World, COLORS, HEIGHT, NAME2ID, CLASSES

IMG_H, IMG_W = 180, 320
CAM_H = 0.7          # camera height (m)
CAM_PITCH = np.deg2rad(14)
HFOV = np.deg2rad(90)
RANGE = 14.0         # max useful range (m)
K = len(CLASSES)


class Camera:
    def __init__(self, world: World, h: int = IMG_H, w: int = IMG_W):
        self.w = world
        self.H, self.W = h, w
        f = (w / 2) / np.tan(HFOV / 2)
        self.f = f
        u = (np.arange(w) - w / 2 + 0.5) / f
        v = (np.arange(h) - h / 2 + 0.5) / f
        self.U, self.V = np.meshgrid(u, v)

    # ---------------------------------------------------------- ray geometry
    def ground_points(self, pose):
        """Back-project every pixel to the ground plane. Returns x, y (world), depth, valid mask."""
        x, y, th = pose
        # camera ray in camera frame: (u, v, 1); rotate by pitch (down positive)
        cp, sp = np.cos(CAM_PITCH), np.sin(CAM_PITCH)
        # forward component and down component after pitch
        fwd = cp - self.V * sp
        down = sp + self.V * cp
        valid = down > 1e-3
        depth = np.where(valid, CAM_H / np.maximum(down, 1e-3), 0.0)
        along = depth * fwd
        lateral = depth * self.U
        wx = x + along * np.cos(th) - lateral * np.sin(th)
        wy = y + along * np.sin(th) + lateral * np.cos(th)
        valid &= (along > 0.3) & (along < RANGE)
        return wx, wy, along, valid

    def observed_cells(self, pose):
        """Cells (i, j) visible in the FOV wedge with occlusion by tall objects (vectorised ray cast)."""
        x, y, th = pose
        w = self.w
        angs = th + np.linspace(-HFOV / 2, HFOV / 2, 121)
        rs = np.arange(0.5, RANGE, w.res * 0.7)
        px = x + rs[None, :] * np.cos(angs)[:, None]
        py = y + rs[None, :] * np.sin(angs)[:, None]
        inb = (px >= 0) & (px < w.size_m) & (py >= 0) & (py < w.size_m)
        i = np.clip((py / w.res).astype(int), 0, w.n - 1)
        j = np.clip((px / w.res).astype(int), 0, w.n - 1)
        c = w.terrain[i, j]
        tall = c == NAME2ID["tree"]
        blocked = (np.cumsum(tall, axis=1) - tall) > 0
        vis = inb & ~blocked & (np.cumsum(~inb, axis=1) == 0)
        key = (i * w.n + j)[vis]
        rr = np.broadcast_to(rs, i.shape)[vis]
        cc = c[vis]
        order = np.argsort(rr, kind="stable")
        key, rr, cc = key[order], rr[order], cc[order]
        uk, first = np.unique(key, return_index=True)
        return {(int(k // w.n), int(k % w.n)): (int(cc[f]), float(rr[f])) for k, f in zip(uk, first)}

    # --------------------------------------------------------------- render
    def render(self, pose, rng: np.random.Generator, cells=None):
        """Return RGB image (H, W, 3) in 0..1 and the ground-truth label image (H, W)."""
        w = self.w
        wx, wy, depth, valid = self.ground_points(pose)
        img = np.zeros((self.H, self.W, 3), dtype=np.float32)
        lab = np.full((self.H, self.W), -1, dtype=np.int16)
        # sky gradient
        sky_top = np.array([0.55, 0.72, 0.95]) * (0.35 + 0.65 * w.sun)
        sky_bot = np.array([0.80, 0.86, 0.95]) * (0.35 + 0.65 * w.sun)
        tt = np.linspace(0, 1, self.H)[:, None, None]
        img[:] = sky_top * (1 - tt) + sky_bot * tt
        # ground
        ii = np.clip((wy / w.res).astype(int), 0, w.n - 1)
        jj = np.clip((wx / w.res).astype(int), 0, w.n - 1)
        inb = valid & (wx >= 0) & (wx < w.size_m) & (wy >= 0) & (wy < w.size_m)
        cls = np.where(inb, w.terrain[ii, jj], 0)
        ground = COLORS[cls]
        # texture + distance haze
        tex = 1.0 + 0.10 * gaussian_filter(rng.standard_normal((self.H, self.W)), 1.0)[..., None]
        haze = np.clip(depth / RANGE, 0, 1)[..., None]
        ground = ground * tex
        # shadows cast by tall objects along sun azimuth (sample terrain "upstream" of the pixel)
        shadow = np.zeros((self.H, self.W), dtype=np.float32)
        for d in (1.0, 2.0, 3.0):
            sx = wx - d * np.cos(w.sun_azimuth)
            sy = wy - d * np.sin(w.sun_azimuth)
            si = np.clip((sy / w.res).astype(int), 0, w.n - 1)
            sj = np.clip((sx / w.res).astype(int), 0, w.n - 1)
            shadow = np.maximum(shadow, (w.terrain[si, sj] == NAME2ID["tree"]).astype(np.float32))
        shade = (1.0 - 0.55 * shadow * (w.sun > 0.4))[..., None]
        light = (0.25 + 0.75 * w.sun)
        ground = ground * shade * light
        ground = ground * (1 - 0.35 * haze) + np.array([0.75, 0.80, 0.85]) * light * 0.35 * haze
        img[inb] = ground[inb]
        lab[inb] = cls[inb]
        # standing objects as billboards (far to near)
        x, y, th = pose
        objs = []
        for (i, j), (c, r) in (cells if cells is not None else self.observed_cells(pose)).items():
            if c in HEIGHT:
                objs.append((r, i, j, c))
        objs.sort(reverse=True)
        cp, sp = np.cos(CAM_PITCH), np.sin(CAM_PITCH)
        for r, i, j, c in objs:
            ox, oy = (j + 0.5) * w.res, (i + 0.5) * w.res
            dx, dy = ox - x, oy - y
            along = dx * np.cos(th) + dy * np.sin(th)
            lateral = -dx * np.sin(th) + dy * np.cos(th)
            if along < 0.5:
                continue
            h = HEIGHT[c]
            # project bottom (z=-CAM_H) and top (z=h-CAM_H)
            def proj(z):
                zc = -z * cp + along * sp       # down component
                fc = along * cp + z * sp        # forward
                u = self.f * lateral / fc + self.W / 2
                v = self.f * zc / fc + self.H / 2
                return u, v
            u0, vb = proj(-CAM_H)
            _, vt = proj(h - CAM_H)
            half = self.f * (w.res * 0.55) / (along * cp)
            ua, ub = int(u0 - half), int(u0 + half)
            va, vb_ = int(max(vt, 0)), int(min(vb, self.H))
            if ub < 0 or ua >= self.W or vb_ <= va:
                continue
            ua, ub = max(ua, 0), min(ub, self.W)
            col = COLORS[c] * light * (0.8 + 0.2 * rng.random())
            img[va:vb_, ua:ub] = col
            lab[va:vb_, ua:ub] = c
        # sensor noise grows in low light; slight blur
        noise_sigma = 0.01 + 0.10 * (1 - w.sun) ** 1.5
        img = img + rng.normal(0, noise_sigma, img.shape)
        img = np.clip(img, 0, 1)
        return img.astype(np.float32), lab

    # ------------------------------------------------------- image features
    @staticmethod
    def image_features(img):
        lum = 0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]
        g = lum[img.shape[0] // 2:]        # ground half
        mean_l = float(g.mean())
        contrast = float(g.std())
        dark = float((g < 0.12).mean())
        bright = float((g > 0.97).mean())
        lap = np.abs(np.diff(g, 2, axis=0)).mean() + np.abs(np.diff(g, 2, axis=1)).mean()
        shadow_ratio = float((g < 0.45 * np.median(g)).mean()) if np.median(g) > 0 else 1.0
        return dict(mean_lum=mean_l, contrast=contrast, dark_frac=dark, bright_frac=bright,
                    sharpness=float(lap), shadow_ratio=shadow_ratio)


class PerceptionStub:
    """Stand-in for the segmentation CNN. Produces per-pixel class probabilities whose
    noise is driven by the rendered image's luminance/contrast, an energy-style unknown
    score, and a frame confidence estimated from image + model statistics."""

    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        self.known = [i for i in range(K) if CLASSES[i][0] != "novel"]

    def infer(self, img, lab):
        feats = Camera.image_features(img)
        # perception noise: low light and heavy shadow degrade logits
        quality = np.clip(2.0 * feats["mean_lum"] + 2.0 * feats["contrast"] - 1.2 * feats["dark_frac"], 0.3, 1.0)
        temp = 0.4 + 1.2 * (1 - quality)
        logits = np.full((IMG_H, IMG_W, K), -3.0, dtype=np.float32)
        valid = lab >= 0
        # true class gets a high logit for known classes; novel objects get diffuse logits
        onehot = np.zeros_like(logits)
        li = np.clip(lab, 0, K - 1)
        onehot[np.arange(IMG_H)[:, None], np.arange(IMG_W)[None, :], li] = 1.0
        logits += 8.0 * onehot * quality
        novel = lab == NAME2ID["novel"]
        logits[novel] = self.rng.normal(-4.0, 0.8, (novel.sum(), K))
        logits[..., NAME2ID["novel"]] = -8.0   # model has no 'novel' output; unknown comes from energy
        logits += self.rng.normal(0, temp, logits.shape)
        logits[~valid] = 0
        m = logits.max(-1, keepdims=True)
        p = np.exp(logits - m)
        p /= p.sum(-1, keepdims=True)
        pred = p.argmax(-1)
        maxp = p.max(-1)
        energy = -np.log(np.exp(logits).sum(-1))
        # unknown score: high energy (no class explains the pixel) -> 1
        unknown = np.clip((energy - 0.2) / 1.6, 0, 1)
        unknown[~valid] = 0
        pred[unknown > 0.55] = NAME2ID["novel"]
        # confidence: learned-regressor stand-in (linear blend calibrated on sim)
        gm = valid[IMG_H // 2:]
        conf = (0.35 * float(maxp[IMG_H // 2:][gm].mean()) + 0.45 * quality
                + 0.20 * (1 - feats["shadow_ratio"]))
        conf = float(np.clip(conf, 0, 1))
        return dict(pred=pred, prob=p, unknown=unknown, conf=conf, feats=feats, valid=valid)
