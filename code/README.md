# DRISHTI-Nav — proof-of-concept simulator

Adaptive risk-aware visual navigation for a GPS-denied outdoor UGV (SIH 2026, PS 26126, BEL).
Pure Python. Runs on macOS/Linux/Windows with no ROS or Gazebo.

## Run

```bash
pip install numpy scipy scikit-image matplotlib imageio imageio-ffmpeg
cd code
python run_demo.py --seed 5 --every 3            # writes output/demo_full.mp4 + snapshots + events_full.txt
python run_demo.py --seed 5 --every 3 --mode baseline
python run_eval.py --runs 15                     # writes output/results.csv and output/summary.md
```

## What is real and what is simulated

| Component | In this proof-of-concept | Planned full stack (ROS 2 + Gazebo) |
|---|---|---|
| World | 80×80 m grid at 0.5 m: grass, dirt, gravel, mud belt, rocks, tree line, ditch, spawnable objects, sun intensity | Gazebo Harmonic outdoor world |
| Camera | Pinhole perspective render of the terrain (billboards for rocks/trees/novel objects), cast shadows, low-light noise | Gazebo RGB-D camera |
| Perception | **Stub**: per-cell class probabilities whose noise is driven by the *rendered image's* luminance/contrast; energy-score unknown detection; confidence from image + model statistics | SegFormer-B0 / Fast-SCNN trained on auto-labelled sim frames + RUGD/RELLIS-3D |
| Localisation | **Stub** visual odometry: drift grows when few trackable features are in view; health signal; ATE reported vs ground truth | RTAB-Map RGB-D + robot_localization EKF |
| Risk map | **Real**: multi-layer grid (class belief, obstacle log-odds, unknown, confidence, last-seen), Bayesian evidence accumulation, built in the odometry frame | Same code |
| Events | **Real**: snapshot-based path corridor change detection (E1–E4), hold-then-escalate | Same code |
| Planner | **Real**: A* on `1 + λ·risk²` (events only), 52-arc local planner at 10 Hz, confidence-band governor with hysteresis | Same code |
| Evaluation | **Real**: seeded scenarios, three planner variants, CSV metrics | Same harness |

Modes: `full` (risk-aware + governor), `risk_only` (risk-aware, governor off), `baseline` (binary obstacle map, hard argmax, unknown ignored, constant speed).

## Layout

```
drishti_nav/world.py         terrain, classes, risk table, spawning, sun
drishti_nav/sensor.py        camera renderer, image features, perception stub
drishti_nav/localization.py  visual-odometry stub with health signal
drishti_nav/risk_map.py      multi-layer risk map, temporal fusion, cost grid
drishti_nav/planner.py       governor bands, A*, arc-sampling local planner, event manager
drishti_nav/sim.py           closed loop + scenario events + metrics
drishti_nav/viz.py           dashboard renderer
run_demo.py / run_eval.py    scripted demo video, seeded evaluation
```
