# SIH 2026 · PS 26126 (BEL) — Solution Guide
## Adaptive Risk-Aware Visual Navigation for a GPS-Denied Outdoor UGV (software / simulation-first)

*Prepared 28 Sep 2026. Companion to `references/literature_review_hardware_first.md` (the earlier hardware-oriented literature survey). This guide re-plans that material for a simulation-first software deliverable and answers sections A–K of the team brief.*

---

## 0. How to actually win this (read this first)

Most teams on this PS will submit some version of **camera → YOLO → ORB-SLAM → A\* → robot**, and most of them will not have it running end to end on judging day. That is the real competition: not the idea, the integration. So the strategy is:

1. **A working closed loop beats a clever slide.** Get a virtual UGV driving from A to B in simulation with *any* perception by Week 3, even with ground-truth pose. Everything innovative is layered on top of a loop that already works.
2. **One innovation, made visible and measurable.** Your innovation is *"the planner reasons about risk and about how much it trusts its own eyes."* That is one idea with four visible faces (risk field, unknown regions, confidence gauge, event-driven replanning). Do not present six separate innovations.
3. **Numbers, not adjectives.** Run the same scenario with a baseline binary planner and with yours, 20–30 seeds each. Report collisions, success rate, path length, replan latency. Judges from BEL are engineers. A table of ablation results is worth more than any animation.
4. **The dashboard is the product.** Judges cannot see your code. They see a split screen: camera with segmentation and unknown-region overlay, a bird's-eye risk map with the robot, current and replanned paths, a confidence gauge, and an event log. Build the dashboard early, not at the end.
5. **Have a deployment story.** Same nodes, swap the simulated camera topic for a real one. Show the model's FPS on CPU and (if you can borrow one) a Jetson. Show inference on a real off-road clip (RUGD / RELLIS) as a bonus panel.
6. **Script the demo and record a backup video.** Live demos fail. A scenario file makes obstacle and lighting events fire deterministically. Have the video ready.
7. **Name it.** SIH judges remember names. Suggestions: **DRISHTI-Nav** (दृष्टि = vision) or **RAVEN** (Risk-Aware Visual Environment Navigation). Pick one and use it everywhere.

Team logistics constraint discovered today: your Mac has no ROS or Gazebo. ROS 2 + Gazebo need Ubuntu. Section E addresses this. The short version: at least one team member needs an Ubuntu 24.04 laptop (an NVIDIA GPU helps but is not mandatory), and everyone else can develop in pure Python on macOS against recorded frames because we fix the module interfaces up front.

---

## A. Problem understanding: what BEL is asking for

BEL wants a **software module** that lets a ground vehicle drive itself outdoors, without GPS, using cameras, and not hit anything. They name three deliverables (perception AI, visual SLAM/odometry, path planner) and one success criterion (collision-free A→B). They do **not** ask for a physical robot, a specific simulator, or a specific algorithm. "Lightweight" is mentioned once and matters: they expect this to run on embedded hardware eventually.

Break-down and how the parts connect:

| # | Component | Input | Output | What "good" means here |
|---|---|---|---|---|
| 1 | **Perception** | RGB (+ depth) frame | Per-pixel terrain class, obstacle mask, per-pixel uncertainty, per-frame confidence | Real-time (≥10 FPS), robust to lighting, knows when it does not know |
| 2 | **Visual localization** | Frame sequence (+ wheel odometry) | 6-DoF pose, trajectory, tracking health | Drift low enough to keep the map consistent over a 100–200 m run; detects tracking loss |
| 3 | **Mapping** | Perception output + pose + depth | Bird's-eye risk grid (0–100 per cell), temporal fusion, change events | Updated every frame, remembers static hazards, forgets dynamic ones |
| 4 | **Path planning** | Risk map, pose, goal, confidence | Global route + local trajectory | Trades distance against risk; replans when the world changes |
| 5 | **Collision avoidance** | Local risk map, local trajectory | Corrected trajectory / stop | Reacts within a few hundred ms to a new obstacle |
| 6 | **Control** | Local trajectory, current pose | Linear + angular velocity | Smooth, speed-limited by confidence, respects vehicle kinematics |

How they connect (data flow): the camera frame goes to perception and to localization in parallel. Perception produces labels and uncertainties in the image; localization produces the pose. Mapping uses the pose and depth to project image labels into a world-fixed grid and fuses them over time into a risk map. The planner reads the risk map, the pose, and the confidence to produce a route and a local trajectory. The controller turns the trajectory into wheel commands. The vehicle moves, a new frame arrives, and the loop repeats. Collision avoidance is not a separate box; it is the local planner running on the freshest part of the risk map plus a hard safety stop.

The three challenges in the PS map onto this as: *path detection* = perception + mapping, *visual localization* = localization, *collision avoidance* = mapping + local planner + control.

---

## B. Innovations beyond YOLO + SLAM + A\*

Eight candidates. Each is something a strong student team can build and show. Difficulty is rated for a team that can write PyTorch and Python and is willing to learn ROS 2.

### B1. Continuous risk field from semantic + geometric fusion
- **Problem solved.** Binary occupancy treats mud and grass identically and cannot represent "this is drivable but bad."
- **How.** Each map cell holds a terrain-class distribution (from segmentation) and height statistics (from depth: slope, step height, roughness). Risk = weighted combination of expected terrain risk (`Σ p(class) · risk_table[class]`), geometric risk (slope/step thresholds), obstacle probability, and unknown score. Planner cost = `1 + λ · (risk/100)^p`, with cells ≥ 90 treated as lethal.
- **Why it matters outdoors.** Rocks and ditches are geometry, mud and water are appearance. Fusing both is how you catch a ditch that looks like a shadow and mud that looks like dirt.
- **Feasible?** Yes. It is grid arithmetic.
- **Difficulty.** Medium (projection and temporal fusion need care).
- **Build.** Depth → point cloud → transform by pose → bin into cells → per-cell stats. Risk table in a YAML file so judges can see it is configurable.
- **Demo.** Two routes: a shorter one through mud and gravel, a longer one over grass. UGV takes the longer one. Slide the risk weight λ down and it takes the short one.

### B2. Unknown-aware perception (uncertainty as a map channel)
- **Problem solved.** A model forced to pick a known class calls an unfamiliar object "grass" and drives into it.
- **How.** Three cheap signals combined: (a) **energy score** on the segmentation logits (`−logsumexp(logits)`), which is free and better calibrated than max-softmax; (b) **outlier exposure** in simulation: drop random meshes with random textures into training scenes and label them `novel`, so the model learns an explicit "weird thing" class; (c) optionally a **3-model mini-ensemble** or MC-dropout (4 passes) for pixel-wise disagreement. The per-pixel unknown score becomes a channel in the risk map and receives a configurable risk (default 60, scaled up when confidence is low).
- **Why it matters outdoors.** The training set never contains everything a field contains.
- **Feasible?** Yes. Energy score is one line. Outlier exposure is trivial in a simulator where you control the scene.
- **Difficulty.** Medium. Calibrating thresholds is the fiddly part; do it on a held-out set of never-seen sim objects and report AUROC.
- **Build.** Add the `novel` class, add the energy head, tune a threshold, write the map channel.
- **Demo.** Spawn an object that was never in training (a purple tetrahedron, a fallen barrel). The overlay paints it magenta as "unknown"; the map raises risk; the path bends around it with a wider margin than around a known rock.

### B3. Perception-confidence governor (lighting-aware behaviour)
- **Problem solved.** The stack drives at full speed into a shadowed patch where its segmentation is garbage.
- **How.** Compute a per-frame confidence `C ∈ [0,1]` from two families of features: image quality (mean luminance, contrast, fraction of clipped dark/bright pixels, Laplacian variance for blur, shadow ratio = fraction of pixels below 0.4× median luminance) and model behaviour (mean max-probability over the drivable region, mean entropy, ensemble disagreement, temporal flicker of class labels between consecutive frames). The clever, cheap part: **train a tiny regressor (gradient-boosted trees or a 2-layer MLP) in simulation to predict the frame's actual mIoU from these features**, because in sim you have ground truth for every frame. That gives a calibrated confidence rather than a hand-tuned heuristic. Then a governor maps `C` to behaviour: max speed, inflation radius, risk weight λ, unknown-risk multiplier, and whether to apply CLAHE/gamma pre-processing.
- **Why it matters outdoors.** Lighting is the PS's own named failure mode. This turns it into a first-class signal.
- **Feasible?** Yes. Image statistics are OpenCV one-liners; the regressor trains in minutes.
- **Difficulty.** Medium.
- **Build.** Feature extractor, regressor training script, governor table (three bands), EMA smoothing so behaviour does not flicker.
- **Demo.** Dim the sun mid-run. Confidence gauge drops from ~0.9 to ~0.5. Speed drops, the safety margin visibly widens on the map, the path shifts to the middle of the open grass. Then restore the light and watch it recover.

### B4. Event-driven hierarchical replanning
- **Problem solved.** Running a global planner every frame is wasteful and causes path oscillation; running it never means you drive into the new rock.
- **How.** Global planner (A\* on the risk grid) runs on events only. Local planner (arc sampling, 10 Hz) runs always on a 10 m window. An **event manager** watches: (E1) risk in the current path corridor jumps above a threshold → local detour, escalate to global replan if the detour costs more than X; (E2) accumulated risk change in the corridor exceeds a budget → global replan; (E3) confidence crosses a band boundary → cost function changed → replan; (E4) localization health degraded → stop and recover; (E5) goal reached. Rate-limit global replans to ≥ 1 s apart.
- **Why it matters outdoors.** Things appear (animals, people, fallen branches) and disappear.
- **Feasible?** Yes. It is a state machine plus a corridor mask.
- **Difficulty.** Medium.
- **Build.** Corridor mask along the path, delta-risk accumulator, state machine, timers. Log every event with a timestamp; the log itself is a demo artefact.
- **Demo.** Spawn a rock on the path. Event log prints `E1 corridor_blocked @ 41.2 s → local replan (38 ms)`. Path bends. Judges see the latency number.

### B5. Bayesian temporal fusion with decay (static memory, dynamic forgetting)
- **Problem solved.** Single-frame maps flicker; permanent maps never forget a person who walked away.
- **How.** Obstacle probability per cell is a log-odds update (standard occupancy-grid math) with a decay toward the prior for cells not re-observed, faster for cells classified as dynamic (person, animal). Terrain class evidence uses an exponential moving average of class probabilities. Unknown score decays slowly.
- **Why it matters outdoors.** It is the difference between a map and a screenshot.
- **Feasible?** Yes, standard.
- **Difficulty.** Easy–Medium.
- **Demo.** A person walks across the path and leaves. The map cell goes red, then fades over ~5 s, and the path relaxes back.

### B6. Localization-health-aware behaviour
- **Problem solved.** Visual SLAM loses tracking on featureless grass or during a fast turn, and the robot keeps driving on a wrong pose.
- **How.** Read tracking health from the SLAM system (tracked feature count, inlier ratio, RTAB-Map's odometry quality / "lost" flag). Fuse visual odometry with simulated wheel odometry in an EKF (`robot_localization`). When visual tracking is lost: cap speed, rely on wheel odometry with growing pose uncertainty, inflate map staleness, and if still lost after N seconds, stop and rotate slowly to re-acquire features.
- **Why it matters outdoors.** Sky, grass, and dirt are the three most feature-poor textures in existence.
- **Feasible?** Yes with RTAB-Map + EKF. Harder if you write your own VO (then you compute inlier counts yourself).
- **Difficulty.** Medium.
- **Demo.** Point the camera at open sky/grass or blank out the image for 2 s. Health indicator goes red, UGV slows, pose uncertainty ellipse grows, then recovers.

### B7. Risk-appetite Pareto routing (safest vs shortest)
- **Problem solved.** "Safe" is not a single answer; an operator in search-and-rescue accepts more risk than one in agriculture.
- **How.** Run the global planner with two or three λ values and show the resulting routes together (shortest, balanced, safest) with their expected risk and length. A slider (or a config parameter) picks the operating point.
- **Why it matters.** It makes the risk field *legible* to a human. It also gives judges an interactive moment.
- **Feasible?** Trivial once B1 exists (three planner calls).
- **Difficulty.** Easy.
- **Demo.** Show the three routes. Drag the slider. Route switches.

### B8. Sim-to-real data engine + real-video sanity panel
- **Problem solved.** You cannot collect thousands of labelled outdoor images. Judges will ask whether this works in the real world.
- **How.** Use the simulator's segmentation camera to auto-label every training frame. Randomize sun angle, sky, texture tint, fog, and camera exposure (domain randomization). Fine-tune the same model briefly on RUGD/RELLIS-3D with classes mapped to your scheme. Run inference on a real off-road clip and show it in a side panel.
- **Feasible?** Yes. This is mostly a data pipeline.
- **Difficulty.** Easy–Medium.
- **Demo.** A 20-second panel of real footage with your segmentation and unknown overlay.

Two more worth mentioning, but do not build them unless ahead of schedule:
- **B9. Negative-obstacle (ditch) detection** from depth: a drop in the height map, or a "shadow" of missing/invalid depth beyond an edge, marks a ditch. In simulation, ditches can also be labelled semantically. Geometry is the honest way; do it if the depth pipeline is solid.
- **B10. Self-supervised risk calibration** (future work): record simulated wheel slip / pitch-roll while driving each terrain and learn the risk table instead of hand-writing it. This is the direction of Wild Visual Navigation (ETH, 2023) and RoadRunner (2024). Mention it as the roadmap; do not build it.

---

## C. Evaluation of "Adaptive Risk-Aware Visual Navigation"

**1. Genuinely useful.** Risk-aware traversability (B1), the confidence governor (B3), event-driven replanning (B4), and the dynamic map (B5) are all sound, feasible, and visible. Unknown-aware perception (B2) is useful *if scoped* to energy score + outlier exposure; it is the single most distinctive item.

**2. Redundant (merge these).**
- *Perception confidence* and *lighting-aware navigation* are the same mechanism. Lighting is the cause; confidence is the measurement; the governor is the response. Present one module: **Confidence Governor**.
- *Dynamic risk map* and *environmental change detection* are the same module. Change detection is the difference between map updates in the path corridor. Present one module: **Risk Map + Event Manager**.
- *Unknown-aware* and *confidence* partially overlap. Keep both, but frame them as two scales of one idea: unknown is **per-cell** (where am I unsure), confidence is **per-frame** (how much should I trust this whole frame). Say this sentence to the judges; it shows you understand the difference between spatial and global uncertainty.

**3. Too difficult (do not attempt).**
- True open-set recognition or OOD detection with guarantees. Use energy score + novel class and call it "uncertainty-aware," not "open-set."
- "Investigate cautiously" as an active exploration behaviour (driving closer to look). It is a research topic. Replace with "slow down and give it a wider margin."
- Writing your own full visual SLAM with loop closure. Use RTAB-Map. Write a small visual odometry only as a learning exercise / fallback.
- Photorealistic simulation. Gazebo/Webots realism is enough because you train in the same simulator.

**4. Meaningful differentiation.** In order: (i) unknown regions in the map, (ii) a confidence gauge that visibly changes the vehicle's behaviour, (iii) a risk field that chooses a longer, safer route, (iv) an event log with replan latencies. Nobody else will show (i) and (ii).

**5. Combine.** Risk table + geometry + unknown + confidence → *one* risk map with layers. Global + local + events → *one* planner module with a state machine. Six ideas become three modules: **Perception with uncertainty**, **Risk map with events**, **Adaptive planner with governor**. That is what the architecture in Section D shows.

**6. Remove to stay achievable.**
- A separate YOLO detector. Segmentation already labels rocks and trees. Add YOLO only if you want instance tracking of people/animals (good-to-have).
- D\* Lite. A\* on a 400×400 grid re-runs in tens of milliseconds with a C-backed implementation. Say "incremental planners like D\* Lite are a drop-in upgrade."
- Monocular depth networks. Use the simulated RGB-D camera (a RealSense/ZED stands in for it on real hardware). Keep a ground-plane homography (IPM) as the monocular fallback for terrain only.
- "Trigger additional visual analysis." Replace with CLAHE/gamma pre-processing when luminance is low. Cheap, visible, honest.

---

## D. Final architecture

```
                 ┌──────────────────────────────────────────────────┐
                 │  SIMULATOR (Gazebo Harmonic + ROS 2 Jazzy)         │
                 │  outdoor world · UGV (diff/skid-steer) · RGB-D cam │
                 │  segmentation cam (training only) · wheel odom     │
                 │  scenario scripts: spawn obstacle, change light    │
                 └───────┬────────────────────────┬─────────────────┘
                         │ /camera/rgb, /camera/depth     │ /wheel_odom, GT pose (eval only)
          ┌──────────────▼──────────────┐   ┌─────────────▼──────────────┐
          │ 1. PERCEPTION (10–20 Hz)     │   │ 2. LOCALIZATION             │
          │ • pre-process (CLAHE if dark)│   │ • RTAB-Map RGB-D odometry   │
          │ • terrain segmentation       │   │ • EKF fuse w/ wheel odom    │
          │   (8 classes, SegFormer-B0 / │   │ • tracking-health signal    │
          │   Fast-SCNN, ONNX)           │   │ → pose, covariance, health  │
          │ • unknown score (energy +    │   └─────────────┬──────────────┘
          │   novel class [+ ensemble])  │                 │
          │ • confidence C (learned      │                 │
          │   frame-quality regressor)   │                 │
          └──────────────┬──────────────┘                 │
                         │ seg, unknown, C                 │ pose
          ┌──────────────▼─────────────────────────────────▼──────────────┐
          │ 3. RISK MAP + EVENT MANAGER (per frame)                         │
          │ • depth → points → world frame → cells (0.25 m)                  │
          │ • per cell: class EMA, obstacle log-odds, height stats,          │
          │   unknown EMA, confidence-at-observation, last-seen              │
          │ • risk = f(terrain, geometry, obstacle, unknown, staleness)      │
          │ • corridor change detection → events E1..E5                      │
          └──────────────┬────────────────────────────────┬────────────────┘
                         │ risk grid (0–100), events        │
          ┌──────────────▼──────────────┐   ┌─────────────▼──────────────┐
          │ 4. ADAPTIVE PLANNER          │   │ 5. BEHAVIOUR GOVERNOR       │
          │ • global: A* on cost grid    │◄──│ C, loc-health → v_max,      │
          │   cost = 1 + λ(C)·risk^p     │   │ inflation, λ, unknown-risk, │
          │   (on events only)           │   │ state: NORMAL/CAUTIOUS/     │
          │ • local: arc sampling 10 Hz  │   │ CONSERVATIVE/RECOVER/STOP   │
          │   over 10 m window           │   └─────────────────────────────┘
          │ • safety stop on lethal cell │
          └──────────────┬──────────────┘
                         │ local trajectory
          ┌──────────────▼──────────────┐        ┌────────────────────────┐
          │ 6. CONTROLLER (20 Hz)        │        │ 7. DASHBOARD + EVAL     │
          │ pure-pursuit on trajectory   │        │ camera+overlay · risk   │
          │ speed ≤ v_max(C)             │        │ map · paths · gauges ·  │
          │ → /cmd_vel                   │        │ event log · metrics CSV │
          └─────────────────────────────┘        └────────────────────────┘
```

Module by module:

1. **Perception.** One lightweight segmentation network with 8 classes: `smooth` (grass/short vegetation), `rough` (dirt/gravel), `soft_hazard` (mud/water), `rock`, `vegetation_obstacle` (tree/bush), `ditch` (labelled in sim; geometry is the real detector), `sky`, `novel`. Output: class map, per-pixel unknown score, per-frame confidence, plus the feature vector used for confidence (logged for the metrics). Pre-processing applies CLAHE + gamma when mean luminance falls below a threshold. Runs as ONNX on GPU if available, CPU otherwise at reduced resolution (320×480 is enough).

2. **Localization.** RTAB-Map in RGB-D mode gives visual odometry with local loop closure and publishes `map→odom`. `robot_localization` EKF fuses it with simulated wheel odometry to survive tracking loss. Tracking health is derived from RTAB-Map's odometry info (feature count, inliers, lost flag). Ground-truth pose from the simulator is recorded *only* for computing localization error.

3. **Risk map + event manager.** A rolling 100×100 m grid at 0.25 m (160k cells) anchored in the map frame, stored as NumPy arrays (one per layer). Every frame: project depth pixels with their class label into cells, update layers, recompute risk for touched cells. The event manager compares the new risk against the previous risk inside the current path corridor and emits events.

4. **Adaptive planner.** Global A\* through the cost grid using a C-backed minimum-cost-path routine (`skimage.graph.route_through_array` or `pyastar2d`), invoked only on events. Local planner samples ~40 (v, ω) arcs over a 2 s horizon, rolls them out, and scores each on accumulated risk, distance to the global path, heading progress, and speed; arcs entering inflated lethal cells are rejected. If no arc is feasible, the vehicle stops and requests a global replan.

5. **Behaviour governor.** A small table indexed by confidence band and localization health, producing planner and controller parameters. Three bands:

   | Band | C | v_max | Inflation | λ | Unknown risk × | Notes |
   |---|---|---|---|---|---|---|
   | NORMAL | ≥ 0.75 | 1.0 m/s | 0.3 m | 2 | 1.0 | |
   | CAUTIOUS | 0.5–0.75 | 0.6 m/s | 0.5 m | 4 | 1.5 | CLAHE on |
   | CONSERVATIVE | < 0.5 | 0.3 m/s | 0.7 m | 8 | 2.0 | prefer risk < 30 cells; stop if C < 0.3 for 3 s |
   | RECOVER | loc health lost | 0 → rotate | – | – | – | wheel-odom dead-reckoning, timeout → STOP |

6. **Controller.** Pure pursuit (or simply track the first arc's (v, ω)) with a speed cap from the governor and a hard stop if any cell within a 0.5 m disc ahead is lethal. Publishes `/cmd_vel`.

7. **Dashboard + evaluation.** Foxglove Studio for ROS-native panels (fastest to get running) and a small custom web page for the judge-facing view (camera + overlays, risk map, confidence gauge, state, event log). An evaluation node writes one CSV row per run with all metrics in Section K.

Why this is better than the linear chain in the brief: perception and localization run **in parallel** rather than in series; the confidence governor **feeds back** into both the planner's cost function and the controller's speed, which is the actual novelty; and the global planner is **event-triggered** rather than in the per-frame loop.

---

## E. Technology stack

### Simulation

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Gazebo (Harmonic) + ROS 2 (Jazzy)** | Industry standard; RGB-D and **segmentation camera sensors built in** (free labels); RTAB-Map, EKF, Foxglove, rosbag all plug in; strongest deployment story for BEL | Ubuntu only; setup friction; ROS learning curve; outdoor visuals are plain | **Recommended** if ≥ 1 member has (or will install) Ubuntu 24.04 |
| **Webots + Python controller** | Runs natively on macOS/Windows/Linux; simple Python API without ROS; camera segmentation and range-finder built in; supervisor API scripts lights and spawns objects; optional ROS 2 bridge later | Must write your own VO (no RTAB-Map without ROS); smaller ecosystem; slightly less "industrial" in judges' eyes | **Fallback / Plan B** for a Mac-heavy team; decision gate end of Week 2 |
| CARLA | Photorealistic | Urban driving; terrain and off-road support weak; heavy GPU | No |
| Isaac Sim | Best visuals, synthetic data tools | Needs RTX GPU, heavy, steep | No (mention as future) |
| Unity / Unreal | Photorealistic terrain, Unity Perception gives labels | Need a Unity/Unreal developer; ROS bridging is extra work; time sink | No unless a member already builds games |
| Custom Python 2.5D sim | Fastest | Camera feed is fake; judges will discount it | Only as the unit-test harness for planner/map (do build this, it takes a day) |

Pairings (Sept 2026): ROS 2 Jazzy + Gazebo Harmonic on Ubuntu 24.04 (both LTS, supported into 2028–29). Humble + Fortress works but Fortress reaches end-of-life this month. On macOS, Gazebo does not run well; use a Linux laptop, dual-boot, or a cloud Ubuntu VM with a virtual desktop. Docker on Mac cannot give you a GPU-rendered Gazebo window; do not spend days on that.

### Vision

| Need | Choice | Why |
|---|---|---|
| Terrain segmentation | **SegFormer-B0** (3.7 M params, HuggingFace) or **Fast-SCNN** (~1.1 M) via `segmentation_models_pytorch` FPN with a MobileNetV3 encoder | Tiny, real-time on CPU at 320×480, ONNX-exportable; the literature review's OFFSEG/FastSCNN results show 80–87 % mIoU on 4–6 class off-road schemes |
| Uncertainty | Energy score (free) + `novel` class; optional 3-seed ensemble | Zero to 3× cost; no new architecture |
| Confidence | OpenCV image stats + LightGBM/sklearn regressor | Trains in minutes, explains itself |
| Discrete objects (optional) | YOLO11n / YOLOv8n (Ultralytics) | Only if you want person/animal tracking; AGPL licence, note for BEL |
| Depth | Simulated RGB-D camera (RealSense/ZED analogue) | Metric, robust; on real hardware ZED/RealSense compute depth on-device |
| Runtime | ONNX Runtime (CPU/CUDA), TensorRT if a Jetson is available | Report FPS for both |

### Localization

| Option | Verdict |
|---|---|
| **RTAB-Map (RGB-D)** | **Primary.** `apt install ros-jazzy-rtabmap-ros`, publishes odometry + TF, gives loop closure and a health signal. Lowest integration risk. |
| ORB-SLAM3 | More accurate, but a C++ build with fragile ROS 2 wrappers. Use only if a member already has it running. |
| Own RGB-D visual odometry (ORB + PnP RANSAC + keyframes, ~300 lines Python) | **Build it anyway** as the fallback and as the thing you can explain at the whiteboard. Fuse with wheel odometry. Report its drift honestly next to RTAB-Map's. |
| `robot_localization` EKF | Yes, fuses VO + wheel odom. |

### Planning

| Option | Verdict |
|---|---|
| **A\*** on the risk grid (C-backed) | **Global.** Tens of ms on 400×400. |
| D\* Lite | Not needed; mention as upgrade. |
| RRT/RRT\* | Wrong tool for a grid with continuous costs. |
| **DWA / arc sampling** | **Local.** Write your own 100-line version; you control the risk term. |
| MPPI | Elegant, but tuning eats a week. Optional. |
| Nav2 | Full stack exists, but folding a multi-layer risk field into its costmap means C++ plugins. Use Nav2 only if the ROS member is strong; otherwise your own Python planner is easier to demo and explain. |

### Recommended combination for a college SIH prototype
**Ubuntu 24.04 · ROS 2 Jazzy · Gazebo Harmonic · Python 3.12 nodes (rclpy) · PyTorch → ONNX Runtime · SegFormer-B0 · RTAB-Map + robot_localization · NumPy risk map · A\* (skimage/pyastar2d) + arc-sampling local planner · Foxglove + a small FastAPI/WebSocket dashboard · pytest + a 2-D NumPy toy world for planner tests.**

Fallback if the ROS/Gazebo gate is missed by end of Week 2: **Webots R2025 + Python controllers + own RGB-D VO**, same module interfaces.

---

## F. What to build: the MVP

### Must have (the demo does not exist without these)
1. **Simulation world**: ~120×120 m terrain with grass, dirt/gravel patches, a mud/water patch, scattered rocks, a tree line, one ditch, a directional sun with shadows. A four-wheel diff-drive/skid-steer UGV with an RGB-D camera (640×480, 90° HFOV) at ~0.6 m height, wheel odometry, ground-truth pose published for evaluation only.
2. **Scenario scripting**: a YAML file with start, goal, timed/trigger-line events (`spawn rock at (x,y) when robot crosses x=40`, `set sun intensity 0.25 at t=80 s`). One command runs a scenario N times with seeds.
3. **Perception node**: segmentation (8 classes) + unknown score + confidence, published as images/floats; ≥ 10 FPS on the demo laptop.
4. **Localization**: RTAB-Map + EKF, publishing pose; localization error logged against ground truth.
5. **Risk map node**: multi-layer grid, risk 0–100, published as an OccupancyGrid-like message; corridor change detection with events.
6. **Planner + governor + controller**: global A\* on events, local arc sampler at 10 Hz, confidence-banded parameters, safety stop.
7. **Dashboard**: camera with overlays (class colours, unknown in magenta), risk map with robot, trajectory, global path, alternative path, confidence gauge, speed, state, event log.
8. **Dynamic obstacle demo**: obstacle spawned mid-run → detected → map updated → replanned → avoided, with latency printed.
9. **Lighting demo**: sun dimmed mid-run → confidence drops → band changes → speed and margins change → recovers.
10. **A→B evaluation**: ≥ 20 seeded runs each for baseline (binary obstacle grid + shortest path) and full system; metrics table.

### Good to have (each adds a judging moment)
- Unknown-object demo with a never-seen mesh (B2 full version).
- Pareto routes with a risk-appetite slider (B7).
- Localization-loss recovery demo (B6).
- Real off-road clip inference panel (B8).
- 3-model ensemble disagreement layer.
- Dynamic person/animal that walks through and fades from the map (B5 demo).
- Jetson or Raspberry Pi 5 FPS numbers for the model.
- Own visual-odometry implementation shown alongside RTAB-Map.

### Optional / future work (slides only)
- Self-supervised risk learning from traversal (B10).
- Negative-obstacle detection from depth (B9) if depth pipeline is clean.
- Nav2 costmap plugin packaging.
- Thermal/IR camera for night; IMU-aided VIO.
- Physical UGV deployment (Jetson Orin Nano + RealSense D435i), which the earlier literature review already scopes.

---

## G. Dataset requirements

You will not label thousands of images by hand, and you do not need to.

| Purpose | Primary source | Secondary / public | Notes |
|---|---|---|---|
| Terrain classification & path detection | **Simulator auto-labels** (segmentation camera). Target 3–5k frames with domain randomization (sun angle, intensity, sky, texture tint, fog, exposure). | **RUGD** (~7.4k frames, 24 classes, small UGV), **RELLIS-3D** (6.2k labelled images, 20 classes), **GOOSE** (2023, ~10k labelled pairs, 64 classes), **Freiburg Forest** (366 images, small but clean), **YCOR / Yamaha-CMU** (1k images, 8 classes) | Map every public class to your 8-class scheme with a lookup table. Fine-tune 1–2 epochs on real data after sim training. |
| Obstacle detection | Same segmentation data (rock, tree, novel classes) | RUGD/RELLIS rock/tree/log classes | Only if you add YOLO: COCO-pretrained YOLO already detects people, animals, vehicles. |
| Unknown / novel detection | **Sim outlier exposure**: 30–50 random meshes (primitives, free 3-D models) with random textures, labelled `novel`; hold out 10 shapes never seen in training for evaluation | Anomaly benchmarks for inspiration only: Lost-and-Found, Fishyscapes, SegmentMeIfYouCan (road scenes) | Report AUROC of the unknown score on held-out shapes. |
| Lighting variation | **Sim**: sun intensity 0.1–1.0, elevation 10°–80°, shadows on/off, fog density; plus image-space augmentation (gamma, brightness, contrast, shadow masks) | **ORFD** (~12k RGB-D frames across sunny/rainy/foggy/snowy and bright/daylight/twilight/dark conditions) | ORFD is the best public set for the "confidence vs lighting" plot. |
| Confidence regressor training | **Sim** frames with ground-truth mIoU per frame under varied lighting | ORFD subsets by lighting | Target: correlation between predicted and actual mIoU ≥ 0.7. |
| Localization evaluation | **Sim** ground-truth pose | (none needed) | Report ATE/RPE per run. |

Practical rules: keep a class-mapping YAML in the repo; keep a `datasets/README.md` with licences (RUGD and RELLIS are research-use; ORFD is research-use; GOOSE is CC BY-SA); never claim you trained on thousands of real images unless you did.

---

## H. Demo scenario (4 minutes, scripted)

Screen layout throughout: left = camera with segmentation + unknown overlay; right = bird's-eye risk map with robot, trajectory, global path (white), alternative path (grey), local trajectory (green); top strip = confidence gauge, speed, band/state, localization health; bottom strip = event log with timestamps.

| Time | Stage | What the judge sees | What you say |
|---|---|---|---|
| 0:00 | Setup | Map with A and B; two candidate routes: short via mud/gravel, long via grass; risk values shown | "Shortest path crosses mud (risk 70). Our planner picks the grass route at +14 % length." |
| 0:20 | Start | UGV moves; overlay colours terrain; risk map fills in front of it; trajectory grows; pose vs ground-truth error shown in corner | "Every cell carries terrain, geometry, unknown score, and how confident the camera was when it saw it." |
| 0:50 | Sudden obstacle | Rock spawns 8 m ahead on the path. Overlay marks it, map cell turns red, event log prints `E1 corridor_blocked → local replan 38 ms`, path bends, UGV passes with margin | "Global plan untouched. Local replan in under 50 ms." |
| 1:20 | Unknown object | A purple tetrahedron (never in training) appears. Overlay paints it magenta "unknown", map assigns risk 60, path curves around it with a wider berth than around the rock | "It does not know what this is. It does not pretend to. It gives it space." |
| 1:50 | Baseline comparison (pre-recorded, 15 s side-by-side) | Same scenario with a binary obstacle planner: drives straight through the mud patch and clips the unknown object | "Same world, same obstacles. Binary planner collides 6 of 20 runs. Ours 0 of 20." |
| 2:10 | Lighting change | Sun dims and shadows lengthen. Confidence gauge falls 0.92 → 0.55. Band flips to CAUTIOUS. Speed drops, inflation ring widens on the map, path shifts to the widest grass corridor, CLAHE pre-processing switches on (overlay stays clean) | "It measures how much it trusts its own eyes and drives accordingly." |
| 2:40 | Localization stress (optional) | Camera faces open sky for 2 s; health goes red; UGV slows to dead-reckoning; recovers and re-localizes | "No GPS, no lidar. When vision degrades, it knows." |
| 3:00 | Light restored | Confidence climbs; band returns to NORMAL; speed resumes | |
| 3:20 | Arrival | UGV reaches B. Metrics card: success, 0 collisions, path length ratio, mean risk traversed, replan latency, localization ATE, FPS | "Every number here comes from 20 seeded runs, not this one run." |
| 3:40 | Deployment slide | ONNX model FPS on laptop CPU / GPU / (Jetson if available); real-footage inference panel | "Same nodes run on a Jetson with a RealSense." |

Better demo ideas over the brief's version: (1) the side-by-side baseline is the single most persuasive 15 seconds you can show; (2) let a judge pick where the obstacle spawns by clicking on the map; (3) the risk-appetite slider gives them a hands-on moment; (4) keep a pre-recorded full run as the fallback if the live sim hiccups.

---

## I. Innovation vs complexity (trade-offs, not a ranking)

| Feature | Innovation | Difficulty | Demo impact | Keep? | Trade-off to weigh |
|---|---|---|---|---|---|
| Terrain segmentation (lightweight net) | Low | Easy–Medium | Medium | **Yes, core** | Foundation for everything; sim auto-labels make it cheap |
| YOLO obstacle detection | Low | Easy | Low–Medium | **Optional** | Redundant with segmentation; only for person/animal instances |
| Visual SLAM (RTAB-Map) | Medium | Medium (ROS) / Hard (own) | High | **Yes** | Integration, not invention; write a small VO to show understanding |
| Risk map (semantic + geometric) | High | Medium | High | **Yes, core** | Projection bugs eat time; test on a 2-D toy world first |
| Temporal fusion with decay | Medium | Easy–Medium | Medium | **Yes** | Small effort, prevents flicker, enables dynamic obstacles |
| Unknown detection (energy + novel class) | High | Medium | High | **Yes, scoped** | Threshold calibration is fiddly; ensemble version is ×3 cost |
| Confidence governor (lighting-aware) | High | Medium | High | **Yes, core** | Needs the sim lighting pipeline; the learned regressor is the differentiator |
| Event-driven replanning | High | Medium | Very high | **Yes, core** | State machine must be robust; log everything |
| Pareto risk-appetite routes | Medium | Easy | High | **Yes (cheap)** | Three planner calls and a slider |
| Localization-health behaviour | Medium | Medium | Medium–High | **Good to have** | Depends on SLAM exposing health |
| Sim-to-real data engine + real clip | Medium | Easy–Medium | Medium–High | **Good to have** | Answers the "does it work in reality" question |
| Negative-obstacle from depth | Medium | Medium–Hard | Medium | **Only if ahead** | Depth edge artefacts cause false ditches |
| Self-supervised risk learning | High | Hard | Medium | **Slides only** | Research-level; roadmap item |
| Nav2 integration | Low | Medium–Hard | Low | **Optional** | Impresses ROS people, adds no visible behaviour |
| Own SLAM from scratch | High | Hard | High if it works | **No** | Highest schedule risk in the whole project |

---

## J. Team division (6 people) and dependencies

Assume ~10 weeks to the finale. Compress proportionally if your institute's internal hackathon is earlier; the Week 3 milestone (A→B with ground-truth pose) is the one to protect.

| Member | Workstream | Owns | Depends on |
|---|---|---|---|
| **M1 Perception** | Segmentation model, unknown score, confidence regressor, ONNX export, FPS | `perception/` | M4's auto-labelled dataset (Week 1–2); M6's class-mapping for public data |
| **M2 Localization** | RTAB-Map + EKF bring-up, health signal, own VO fallback, ATE/RPE evaluation | `localization/` | M4's world with camera + wheel odom; ground-truth pose topic |
| **M3 Mapping & planning** | Risk map, projection, temporal fusion, event manager, A\*, local planner, governor, controller, 2-D toy world for tests | `risk_map/`, `planner/` | Interface contract (Week 1); M1 outputs (Week 3+); M2 pose (Week 4+); until then uses GT pose and GT segmentation |
| **M4 Simulation** | Gazebo world, UGV model, sensors, segmentation camera, lighting and spawn services, scenario runner, domain randomization, dataset export | `sim/`, `scenarios/` | Nothing; is the critical path in Weeks 1–2 |
| **M5 Dashboard & integration** | Foxglove layout, web dashboard, launch files, message definitions, CI, bag recording/replay, demo script | `dashboard/`, `launch/` | Interface contract (Week 1); everyone's topics |
| **M6 Data, evaluation, docs** | Public dataset download + class mapping, evaluation harness, baseline planner, metrics CSV/plots, ablations, PPT, video, README | `eval/`, `docs/` | M4's scenario runner (Week 3); M3's baseline switch |

Dependency graph (arrows = "needs"):
```
M4 sim world ──► M1 dataset ──► M1 model ──► M3 map (real seg) ──► M5 dashboard ──► M6 eval/ablation
M4 sim world ──► M2 SLAM ──────────────────► M3 map (real pose) ─┘
M5 interface contract (Week 1) ──► everyone
M3 toy world (Week 1) lets M3 work with no sim at all
```

Weekly plan:

| Week | Milestone |
|---|---|
| 1 | Ubuntu + ROS 2 + Gazebo installed on ≥ 1 machine; repo skeleton; **interface contract** signed off (topics, message types, frames, units); world v0 with camera; M3's 2-D toy world + A\* + arc sampler passing tests; M6 downloads RUGD/RELLIS/ORFD |
| 2 | Segmentation camera auto-labelling exports 2k frames; UGV drives on `/cmd_vel`; bag recorded; M1 trains model v0 on sim data; M2 has RTAB-Map publishing a pose. **Gate: if no camera frames reach a Python node and no `/cmd_vel` moves the robot, switch to Webots.** |
| 3 | **First A→B run** with GT pose + GT segmentation through risk map + planner + controller. Dashboard v0 (Foxglove). |
| 4 | Swap in real perception and RTAB-Map pose. Localization error logged. Risk table and geometry layer tuned. |
| 5 | Unknown score + novel class; confidence regressor; governor bands wired to planner and controller. |
| 6 | Event manager; obstacle spawn and lighting events in scenario runner; replanning demo works. |
| 7 | Web dashboard; Pareto routes; localization-health recovery; real-clip panel. |
| 8 | Evaluation harness; baseline planner; 20-seed runs; ablation table; FPS/CPU measurements. |
| 9 | Polish, demo script rehearsal ×5, backup video, PPT, README, judge Q&A prep. |
| 10 | Buffer. Fix what broke. Do not add features. |

Interface contract (put this in `docs/INTERFACES.md` in Week 1):

| Topic | Type | Producer → Consumer | Rate |
|---|---|---|---|
| `/camera/rgb`, `/camera/depth`, `/camera/camera_info` | sensor_msgs/Image, CameraInfo | Sim → Perception, Localization | 15–30 Hz |
| `/wheel_odom` | nav_msgs/Odometry | Sim → EKF | 50 Hz |
| `/gt/pose` | geometry_msgs/PoseStamped | Sim → Eval only | 50 Hz |
| `/perception/seg` | Image (mono8 class ids) | Perception → Risk map, Dashboard | 10–20 Hz |
| `/perception/unknown` | Image (32FC1, 0–1) | Perception → Risk map, Dashboard | same |
| `/perception/confidence` | custom `Confidence` {value, band, features[]} | Perception → Governor, Dashboard, Eval | same |
| `/odom`, TF `map→odom→base_link→camera` | nav_msgs/Odometry, tf2 | Localization → all | 20+ Hz |
| `/localization/health` | custom {tracked_features, inliers, lost:bool} | Localization → Governor | 10 Hz |
| `/risk_map` (+ `/risk_map/layers/*`) | nav_msgs/OccupancyGrid (0–100 = risk) | Risk map → Planner, Dashboard | 5–10 Hz |
| `/events` | custom `Event` {type, t, cell, detail} | Event manager → Planner, Dashboard, Eval | async |
| `/plan/global`, `/plan/alternatives`, `/plan/local` | nav_msgs/Path | Planner → Controller, Dashboard | on event / 10 Hz |
| `/governor/state` | custom {band, v_max, inflation, lambda} | Governor → Planner, Controller, Dashboard | 10 Hz |
| `/cmd_vel` | geometry_msgs/Twist | Controller → Sim | 20 Hz |
| `/metrics` | custom / JSON string | Eval → Dashboard, CSV | 1 Hz |

Suggested repo layout:
```
SIH-126/
  docs/            SOLUTION_GUIDE.md · INTERFACES.md · references/ · slides/
  sim/             gazebo worlds, UGV model (URDF/SDF), sensor configs, launch
  scenarios/       *.yaml (start, goal, events, seeds) + runner
  perception/      model, training, export, confidence, node
  localization/    rtabmap launch, ekf config, own_vo/, node
  risk_map/        layers, projection, fusion, events, node
  planner/         global, local, governor, controller, node, toy_world/
  dashboard/       foxglove layout, web/
  eval/            harness, baselines, metrics, plots
  datasets/        README with licences + class mapping (no data committed)
  tests/
```

---

## K. Innovation statement and metrics

**1. One line.**
A camera-only navigation stack for GPS-denied outdoor UGVs that plans over a continuously updated *risk field* and adapts its speed, margins, and route to how much it trusts its own perception.

**2. Thirty seconds.**
Existing vision-based navigation stacks classify the world into "free" and "blocked" and drive the shortest free path at full speed, whether the camera is looking at sunlit grass or a shadowed patch of mud next to something it has never seen before. DRISHTI-Nav replaces that binary map with a risk field that fuses terrain type, geometry, and uncertainty, and it measures its own perception confidence every frame. When confidence drops, the vehicle slows, widens its margins, and prefers safer ground. When the world changes, it replans locally in tens of milliseconds. It reaches its goal without collisions in simulation across lighting changes, sudden obstacles, and unknown objects, and every claim is backed by seeded runs against a baseline.

**3. One minute.**
The stack has three modules. *Perception with uncertainty*: a 3.7-million-parameter segmentation network labels eight terrain and obstacle classes, an energy-based score flags pixels it cannot explain, and a learned frame-quality regressor, trained in simulation where ground truth is free, predicts how accurate this frame's segmentation will be. *Risk map with events*: depth and pose project those labels into a bird's-eye grid whose cells carry terrain, geometry, obstacle probability, unknown score, and observation confidence, fused over time so static hazards persist and dynamic ones fade; an event manager watches the current path corridor and fires replan events only when something meaningful changed. *Adaptive planner with governor*: a global A\* over the risk-weighted cost grid runs on events, a local arc-sampling planner runs at 10 Hz, and a governor maps confidence and localization health to speed, inflation, and risk weight. Localization is RGB-D visual SLAM fused with wheel odometry, with a health signal that triggers recovery. The whole loop runs in ROS 2 against a Gazebo world, and the same nodes run unchanged with a real RGB-D camera.

**4. Technical architecture explanation.** See Section D. The two structural differences from the standard chain: perception and localization run in parallel and feed one map; and a confidence signal closes a feedback loop from perception quality to planning and control parameters.

**5. What is genuinely innovative.**
- A **multi-layer risk field** (semantic + geometric + obstacle + unknown + confidence-at-observation) as the single planning substrate, rather than an occupancy grid with an inflation layer.
- **Uncertainty as a spatial map channel**: the planner sees where perception was unsure, not just what it decided.
- A **calibrated, learned perception-confidence signal** (predicting frame mIoU from image and model statistics, trained with free simulator ground truth) driving a behaviour governor.
- **Event-driven hierarchical replanning** with a corridor-based change detector and a visible latency log.
- An **evaluation methodology** (seeded scenarios, baseline ablations, lighting sweeps) that most hackathon entries lack.

**6. What it improves upon.**
- Nav2-style costmaps: binary obstacles + inflation, no notion of terrain quality or perception trust.
- Semantic-to-cost heuristics (OFFSEG/GANav style): produce a traversability map but do not model uncertainty or adapt behaviour to lighting.
- YOLO + monocular-depth avoidance pipelines: reactive and objectless about terrain; no memory, no risk trade-off.
- Continuous replanning stacks: waste compute and oscillate; ours plans when something changed.

**7. Metrics to report** (all from ≥ 20 seeded runs per condition; report mean ± std):

| Metric | Definition | Baseline vs ours |
|---|---|---|
| Navigation success rate | Reached B within time limit, no collision | expect large gap under lighting/unknown scenarios |
| Collision rate | Collisions per run (sim contact sensor) | target 0 for ours |
| Path length ratio | Actual path / straight-line or / shortest-path length | ours slightly higher (that is the point; say so) |
| Mean and max risk traversed | Average and max cell risk under the vehicle | ours much lower |
| Replan latency | Obstacle first visible → new local path published | target < 100 ms |
| Detection latency | Obstacle first visible → cell risk > threshold | target < 200 ms |
| Recovery time after sudden obstacle | Event → vehicle back on a feasible path at speed | target < 2 s |
| Localization error | ATE / RPE vs ground truth over the run | report for RTAB-Map and own VO |
| Perception confidence vs actual mIoU | Pearson correlation on held-out frames across lighting | target ≥ 0.7 |
| Unknown detection quality | AUROC of unknown score on held-out never-seen objects | target ≥ 0.85 |
| Segmentation mIoU | On sim held-out and on RUGD/RELLIS subset | report both |
| Perception FPS / end-to-end loop rate | On demo laptop CPU and GPU (and Jetson if available) | ≥ 10 FPS perception, ≥ 10 Hz control |
| Computational load | CPU %, GPU %, RAM per node | for the "lightweight" claim |
| Global replans per run | Count | shows event-driven planning is not thrashing |

---

## L. Judge Q&A preparation

- **"Why not LiDAR?"** The PS makes cameras primary. Cameras are cheap and dense in semantics. LiDAR is a welcome extra risk-map layer; the architecture accepts it unchanged.
- **"How do you get depth from a camera?"** RGB-D or stereo camera (RealSense/ZED do it on-device). Monocular fallback for terrain: ground-plane homography. We do not depend on monocular depth networks.
- **"Where do risk numbers come from?"** A configurable table informed by terrain type plus geometry thresholds; future work learns it from traversal experience (Wild Visual Navigation, RoadRunner).
- **"What happens at night?"** Confidence falls, the governor goes conservative, and below a floor the vehicle stops. We do not claim night driving; thermal/IR is future work.
- **"What if SLAM fails?"** Health signal → EKF on wheel odometry → slow → stop and rotate to re-acquire. Shown in the demo.
- **"Does it run on embedded hardware?"** Model is 3.7 M parameters, ONNX, X FPS on CPU; literature shows this class of network at 15–20 FPS on Jetson; we report our own numbers.
- **"Is it just Nav2 with a costmap?"** No: multi-layer risk with uncertainty, confidence feedback into planning parameters, event-driven replanning. It can be packaged as a Nav2 costmap layer for deployment.
- **"Sim-to-real?"** Domain randomization in sim, fine-tune on RUGD/RELLIS, real-clip inference shown. We are honest that a field trial is the next step.
- **"How is the unknown score validated?"** AUROC on held-out never-seen objects; we show a failure case too.

---

## M. Immediate next steps (this week)

1. Decide who owns the Ubuntu machine and install ROS 2 Jazzy + Gazebo Harmonic today.
2. Create the repo with the layout above; commit `docs/INTERFACES.md` from Section J.
3. M3 builds the 2-D toy world and gets A\* + arc sampler + a risk table passing unit tests on macOS. This needs no simulator.
4. M4 builds world v0 with an RGB-D camera and a wheel-odom UGV; publish a bag by end of Week 1.
5. M6 downloads RUGD, RELLIS-3D, ORFD and writes the class-mapping YAML.
6. Everyone reads Section D until they can draw it from memory. That drawing is your PPT's core slide.

*References for the cited methods: energy-based OOD (Liu et al., NeurIPS 2020); outlier exposure (Hendrycks et al., ICLR 2019); MC dropout (Gal & Ghahramani, ICML 2016); deep ensembles (Lakshminarayanan et al., NeurIPS 2017); OFFSEG (2021), GANav (RA-L 2022), Wild Visual Navigation (Frey et al., 2023), RoadRunner (ICRA 2024); RTAB-Map (Labbé & Michaud, JFR 2019); ORB-SLAM3 (T-RO 2021); D\* Lite (Koenig & Likhachev, 2002); DWA (Fox et al., 1997). Dataset papers are listed in `references/literature_review_hardware_first.md`.*
