"""Run the scripted judging demo and write an MP4 plus key screenshots.

Usage: python run_demo.py [--out output] [--seed 3] [--every 2]
"""
import argparse, os, json
import numpy as np
import imageio.v2 as imageio
import imageio_ffmpeg

from drishti_nav.sim import Simulator
from drishti_nav.viz import render_dashboard

SCENARIO = [
    {"t": 14.0, "type": "spawn", "cls": "rock", "dist": 7.0, "r": 1.1},
    {"t": 30.0, "type": "spawn", "cls": "novel", "dist": 8.0, "r": 1.0},
    {"t": 46.0, "type": "sun", "value": 0.15},
    {"t": 70.0, "type": "sun", "value": 1.0},
]
SNAPSHOTS = {"01_start": 0.5, "02_obstacle": 15.6, "03_unknown": 31.8, "04_lowlight": 52.0, "05_recovered": 74.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output"); ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--every", type=int, default=2); ap.add_argument("--mode", default="full")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    sim = Simulator(seed=a.seed, mode=a.mode, scenario=SCENARIO)
    writer = imageio.get_writer(os.path.join(a.out, f"demo_{a.mode}.mp4"), fps=10, codec="libx264",
                                ffmpeg_params=["-pix_fmt", "yuv420p"], macro_block_size=1)
    k, taken = 0, set()
    while not sim.done:
        sim.step()
        if k % a.every == 0:
            frame = render_dashboard(sim)
            writer.append_data(frame)
            for name, ts in SNAPSHOTS.items():
                if name not in taken and sim.t >= ts:
                    imageio.imwrite(os.path.join(a.out, f"{name}_{a.mode}.png"), frame); taken.add(name)
        k += 1
    frame = render_dashboard(sim); writer.append_data(frame)
    imageio.imwrite(os.path.join(a.out, f"06_goal_{a.mode}.png"), frame)
    writer.close()
    m = sim.metrics()
    print(json.dumps(m, indent=1))
    with open(os.path.join(a.out, f"events_{a.mode}.txt"), "w") as f:
        for t, kind, d in sim.events.log:
            f.write(f"[{t:6.1f}s] {kind}  {d}\n")
    print("\n".join(open(os.path.join(a.out, f"events_{a.mode}.txt")).read().splitlines()))


if __name__ == "__main__":
    main()
