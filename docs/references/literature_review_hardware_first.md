# Vision-Based Autonomous Navigation for Unmanned Ground Vehicle (Outdoor)
### Problem Statement ID: 26126 | Bharat Electronics Limited | Smart Automation

---

## 1. Problem Restated

Build a camera-only (no GPS, no LiDAR assumed necessary) navigation stack for an outdoor UGV that can:
1. **Detect safe, traversable paths** vs. hazards (rocks, ditches, trees, water, mud).
2. **Localize itself** (position + orientation) without GPS, using vision alone.
3. **Avoid sudden obstacles** dynamically while still making progress toward a destination.

Deliverable: a working **software module** = Perception AI + Visual SLAM/Odometry + Path Planner, demonstrated as collision-free Point-A-to-Point-B navigation.

This breaks cleanly into three coupled subsystems that map directly to the three "expected solution" bullets. Below: what research says works, what's already been built (and is reusable), numbers to target, and a concrete build plan.

---

## 2. Related Work

### 2.1 Terrain / Path Perception (traversability from RGB)

| Work | Approach | Key numbers | Why it matters here |
|---|---|---|---|
| **RUGD Dataset** (Wigness et al., IROS 2019) | 7,546 annotated frames, 24 classes, off-road video from a small UGV | Benchmark dataset | Standard benchmark to train/evaluate your path-segmentation model |
| **RELLIS-3D** (Jiang et al., 2020) | Multimodal (RGB + LiDAR) UGV dataset, 20 classes, 6,235 labeled images, 13,556 LiDAR scans <cite index="17-1">gathered specifically in an off-road environment with annotations for LiDAR scans and images</cite> | Benchmark dataset | Same track (real UGV platform), good for sim-to-real style transfer |
| **OFFSEG** (Viswanath et al., 2021) | Pools the 20/24 fine classes of RELLIS-3D/RUGD into **4 practical classes**: traversable, non-traversable, obstacle, sky <cite index="17-1">to mitigate class imbalance and reflect that off-road driving needs far fewer semantic categories than structured road scenes</cite> | **86.6% mIoU** on RELLIS-3D, **80.2% mIoU** on RUGD using BiSeNetV2 <cite index="13-1">as reported for the OFFSEG framework</cite> | Directly gives you the class scheme + a lightweight backbone (BiSeNetV2) that's real-time capable |
| **GANav** (Guan et al., RA-L 2022) | Transformer-based group-wise attention head that groups terrain by *navigability level* rather than raw semantic identity | **74.44% mIoU** on RELLIS-3D <cite index="64-1">as reported on the RELLIS-3D benchmark</cite>; on-robot test with Clearpath Jackal/Husky showed **+10% navigation success rate, 2–47% better best-surface selection, 4.6–13.9% less trajectory roughness, −37.8% forbidden-region false positives** <cite index="59-1">when GANav's output was fed into a downstream navigation planner on real robots</cite> | Best evidence in literature that *navigability-grouped* segmentation (not raw class-accurate segmentation) is what actually improves downstream driving behavior — a strong design cue |
| **Cross-Scale Decoder w/ Token Refinement** (2026) | Regroups RUGD/RELLIS-3D into 6 navigation-oriented classes (Smooth/Rough/Bumpy/Forbidden/Obstacle/Background) | FastSCNN reaches **85.11 mIoU / 94.77 aAcc** on RUGD-6class <cite index="14-1">using the FastSCNN backbone evaluated on the regrouped RUGD benchmark</cite> | Confirms FastSCNN-class lightweight nets are viable for this exact task |
| **RoadRunner** (ETH Zurich, ICRA 2024) | Learns traversability directly (not via a semantic-to-cost heuristic), fusing camera + elevation | Removes hand-tuned semantic→cost mapping | Good "stretch goal" reference if segmentation-based costing proves too brittle |
| **ORFD dataset** | Free-space/traversability with only 3 classes across varied weather | Purpose-built for exactly your "safe path vs hazard" binary/ternary problem | Good secondary dataset if you want an even simpler traversable/non-traversable model |

**Design takeaway:** don't train a 20-class off-road segmenter — nobody downstream needs it. Collapse straight to a **3–6 class navigability map** (Free/Traversable-rough/Obstacle/Forbidden) the way OFFSEG and the Cross-Scale Decoder paper do. This cuts label effort and lets you use a lightweight real-time backbone (BiSeNetV2 / FastSCNN / PIDNet) instead of a heavy transformer.

### 2.2 Obstacle detection & depth (collision avoidance sensor front-end)

- **Depth Anything V2 + YOLOv11** pipeline for obstacle avoidance: object detector localizes obstacles in the image, monocular depth model estimates range; system achieves reliable avoidance out to **~15 m using only a monocular camera**, deliberately avoiding LiDAR <cite index="38-1">to keep the perception module simple and cost-effective while still enabling reliable obstacle avoidance out to roughly fifteen meters</cite>.
- **Depth-Aware Rover** (2026): pairs a fast detector with an intermittently-run depth model since dense monocular depth is too slow for every frame. Ran **YOLO12n at ~10 FPS** using the NCNN backend on-device while depth inference ran asynchronously in the background <cite index="35-1">with depth estimation running asynchronously at a slow rate while YOLO12n maintained real-time detection at ten hertz using the NCNN backend, an architecture chosen to keep obstacle detection timely while accepting delayed depth feedback for longer-range analysis</cite>. This "fast detector, async depth" split is a very practical embedded pattern.
- **Lightweight monocular depth on Jetson Nano/TX2**: multiple lightweight encoder-decoder MDE networks hit real-time speed on Jetson-class embedded GPUs <cite index="32-1">with implementations achieving real-time speed on mobile platforms such as the Nvidia TX2 or Jetson family</cite>; one human-depth network reported **17.2 FPS on Jetson Nano GPU and 114 FPS with TensorRT optimization** <cite index="33-1">on an NVIDIA Jetson Nano GPU, reaching over a hundred frames per second once optimized with TensorRT</cite>.
- **Monocular obstacle-height estimation** on a quadruped: average obstacle-height RMSE of **0.048 m** in the 0.10–0.20 m obstacle range <cite index="34-1">for obstacle height estimation in that range, with the system achieving an average RMSE and MAE accurate enough to support onboard traversal decisions</cite> — useful precedent if you need "can I drive over this bump" logic, not just "stop/steer around."
- **YOLOv8n on Jetson Orin Nano**: ~18–21 ms average inference at 384×640 input <cite index="50-1">with average inference time around twenty-one milliseconds at fifteen watts power mode, improving to about eighteen milliseconds with a higher-performance power mode enabled</cite> → this alone gives ~45–55 FPS headroom, comfortably real-time for a ground vehicle moving at walking/driving pace.

**Design takeaway:** run detection every frame (YOLO-nano class model, real-time on Jetson), run dense depth only every N frames / in a background thread, and use detection-box + sparse depth-at-box-center rather than a full dense depth map per frame — this is the pattern that actually works on embedded hardware per the literature above.

### 2.3 Visual Localization / Odometry (GPS-free pose)

- **ORB-SLAM3** (Campos et al., IEEE T-RO 2021) — the standard reference system: <cite index="21-1">the first real-time SLAM library able to perform Visual, Visual-Inertial and Multi-Map SLAM with monocular, stereo and RGB-D cameras, using pin-hole and fisheye lens models, and in all sensor configurations it is as robust as the best systems available in the literature and significantly more accurate</cite>. Multiple ready ROS 2 wrappers exist (see §3).
- **ORB-SLAM3 on Jetson Nano** for a mobile robot: validated on EuRoC dataset and real-world robot runs, with **wheel encoders used as ground truth** for comparison <cite index="27-1">where the robot's wheel encoders provided ground truth data that was compared against the output from ORB-SLAM3 to assess its accuracy in a real-world scenario</cite> — a directly applicable low-cost validation methodology for your own testing.
- Add an IMU for **visual-inertial odometry (VIO)** rather than pure VO: literature consistently notes vision alone struggles to give real-time *global* pose without drift correction, and recommends **camera+IMU fusion** for robustness <cite index="27-1">since visual odometry alone cannot provide real-time global pose information, making the fusion of camera and IMU data advantageous</cite>.
- If wheel encoders are available on the UGV chassis (very likely, since it's ground not aerial), **wheel odometry + VIO fusion via an EKF** is the pragmatic, well-trodden path (this is exactly what ROS/Nav2 `robot_localization` is built for).

**Design takeaway:** Use **ORB-SLAM3 in stereo or stereo-inertial mode** if you can afford a stereo/RGB-D camera (Intel RealSense D435i is the most common choice in the repos found — cheap, ROS-native, has IMU). Fuse with wheel odometry via EKF for drift correction; this combination is more robust than any single sensor and is exactly what off-the-shelf ROS 2 packages already support.

### 2.4 Path Planning / Collision Avoidance (vision-informed motion commands)

- **Nav2 (ROS 2 Navigation Stack)**: industry-standard, actively maintained framework — <cite index="43-1">a professional-grade navigation framework for ROS 2 providing algorithms and tools for autonomous mobile robot navigation, including planning, control, and obstacle avoidance, and it supports 2D indoor, outdoor, and 3D navigation scenarios</cite>. Comes with global planners (NavFn/A*, Smac, Theta*) and local controllers (DWB/DWA, TEB, MPPI, Pure Pursuit, RPP) out of the box — you do not need to write a planner from scratch.
- **Feeding vision into Nav2's costmap** (arXiv 2407.18535): a directly relevant reference implementation — pipeline is **RGB-D image → YOLOv8 detection → depth image → point cloud → custom Nav2 local-costmap layer**, integrated transparently as an extra costmap layer without modifying Nav2 core <cite index="45-1">enabling the robot to traverse areas by fusing traversability information into the local costmap through a custom layer that integrates transparently into Nav2's existing layered-costmap architecture</cite>. This is close to a blueprint for your exact "path detection → planner" bridge.
- **Behavior-based obstacle avoidance without GPU/LiDAR**: a 50 Hz ROS control loop combining lightweight monocular depth with reactive behavior control, explicitly targeting resource-constrained platforms <cite index="31-1">integrating monocular depth estimation with behavior-based control to achieve obstacle avoidance and autonomous motion without a GPU or LiDAR, using a computation-efficient depth network for real-time GPU-free inference and a fifty-hertz ROS-integrated control loop for smooth motion planning</cite> — good fallback design if the Jetson-class board is a stretch budget-wise.
- Reference repo `reactive_autonomous_nav`: implements and **benchmarks A\*, Theta\*, RRT, Smac/hybrid global planners against DWA, TEB, MPPI, Stanley, and Pure-Pursuit local controllers** on a TurtleBot4 <cite index="40-1">as a modular planner and controller architecture with pluggable global planners and local controllers, benchmarked against Nav2 and PythonRobotics</cite> — useful for choosing/tuning your own local controller empirically instead of guessing.

**Design takeaway:** don't reinvent path planning — **use Nav2** (global: A*/Smac; local: DWB or TEB), and treat your custom perception output (traversability map + obstacle boxes) as just another **costmap layer**, exactly as demonstrated in arXiv 2407.18535. This is the single highest-leverage integration decision in the whole project.

---

## 3. Existing Open-Source Implementations (build on these, don't start from zero)

| Repo | What it gives you | Link |
|---|---|---|
| `rayguan97/GANav-offroad` | Official GANav code + pretrained weights for RUGD/RELLIS-3D navigability segmentation | github.com/rayguan97/GANav-offroad |
| `ros-navigation/navigation2` | Full Nav2 stack — global/local planners, costmaps, behavior trees, recovery behaviors | github.com/ros-navigation/navigation2 |
| `RoverTech-team/Nav2` | End-to-end **skid-steer rover** reference: SLAM Toolbox → diff-drive controller → Nav2 (NavFn + DWB) → stereo (ZED 2i) perception, full launch files and tuned costmap params <cite index="41-1">forming a ROS 2 Humble autonomous navigation stack for a six-wheel skid-steer rover with real-time motor control and stereo perception, including full Nav2 stack global planning, local planning, costmaps, and behavior-tree-based recovery behaviors</cite> | github.com/RoverTech-team/Nav2 |
| `Robo-Friends-Tech/ROS2_ORB-SLAM3_Odometry` | Drop-in ROS 2 wrapper publishing `/odom` + TF from ORB-SLAM3 for mono/stereo/RGB-D/stereo-inertial, tested with RealSense D435i <cite index="25-1">publishing real-time odometry and TF from mono, stereo, RGB-D, and stereo-inertial cameras and integrating seamlessly with RViz 2 and navigation stacks</cite> | github.com/Robo-Friends-Tech/ROS2_ORB-SLAM3_Odometry |
| `Mechazo11/ros2_orb_slam3` / `gjcliff/ORB_SLAM3_ROS2` | Alternative ROS 2 Humble ORB-SLAM3 wrappers, "bare-bones starting point" style, easier to read/modify than the above | github.com/Mechazo11/ros2_orb_slam3 |
| `abdu7rahman/reactive_autonomous_nav` | From-scratch, pluggable global/local planner implementations (A*, Theta*, RRT, Smac / DWA, TEB, MPPI, Pure Pursuit, Stanley) with Nav2 benchmark comparisons | github.com/abdu7rahman/reactive_autonomous_nav |
| `skunal3318/MapperBot-ROS2` | Minimal, readable full pipeline reference: `LiDAR/vision → SLAM → Map → localization → Nav2 Planner → Controller → cmd_vel`, good as a "read this first" architecture skeleton | github.com/skunal3318/MapperBot-ROS2 |
| Ultralytics `ultralytics/ultralytics` (YOLOv8/v11/v12) | Pretrained nano-size detectors, native TensorRT/ONNX/NCNN export for Jetson — used as-is by nearly every obstacle-detection paper cited above | github.com/ultralytics/ultralytics |
| `UZ-SLAMLab/ORB_SLAM3` | Upstream SLAM engine all the ROS 2 wrappers above depend on | github.com/UZ-SLAMLab/ORB_SLAM3 |

**Practical note on licensing:** ORB-SLAM3 is GPLv3 and Ultralytics YOLO is AGPL-3.0 — fine for a hackathon/prototype, but if BEL wants this productized, flag that a commercial Ultralytics license or a permissively-licensed detector (e.g., a plain PyTorch/ONNX-exported model you train yourself) may be needed later.

---

## 4. Proposed Solution

### 4.1 High-level architecture

```
                         ┌─────────────────────────────────────────────┐
                         │                  UGV HARDWARE                │
                         │  Stereo/RGB-D cam (+IMU) · Wheel encoders ·  │
                         │  Compute (Jetson Orin Nano) · Motor drivers  │
                         └───────────────┬───────────────────────────────┘
                                         │ image stream, IMU, wheel ticks
              ┌──────────────────────────┼────────────────────────────┐
              ▼                          ▼                             ▼
   ┌────────────────────┐    ┌────────────────────────┐   ┌───────────────────────┐
   │  PERCEPTION AI      │    │  VISUAL SLAM/ODOMETRY   │   │  (parallel) Wheel Odom │
   │  - Terrain seg.      │    │  ORB-SLAM3 (stereo-     │   │  + IMU  → EKF fusion   │
   │    (BiSeNetV2/       │    │  inertial or RGB-D)     │   └───────────┬───────────┘
   │    FastSCNN, 4-6cls) │    │  publishes /odom + TF   │               │
   │  - Obstacle detect   │    └──────────┬──────────────┘               │
   │    (YOLOv8n)          │              │  pose estimate                │
   │  - Sparse depth at    │              └───────────┬────────────────────┘
   │    obstacle boxes     │                          ▼
   │    (lightweight MDE)  │              ┌────────────────────────┐
   └──────────┬─────────────┘              │  robot_localization EKF │
              │ traversability map +        │  → fused /odom → /map  │
              │ obstacle list (class,       └────────────┬────────────┘
              │ bbox, range)                              │
              ▼                                           ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │                     NAV2 (ROS 2 Navigation Stack)                 │
   │  Custom costmap layer ← traversability map + obstacle list        │
   │  Global planner: A* / Smac Hybrid   Local controller: DWB / TEB   │
   │  Recovery behaviors: spin, backup, wait                           │
   │  → cmd_vel (linear/angular velocity)                              │
   └───────────────────────────────┬───────────────────────────────────┘
                                    ▼
                          Motor controller → UGV drive
```

### 4.2 Module-by-module

**A. Perception AI (Path Detection + Obstacle Detection)**
- Terrain/path segmentation model: **BiSeNetV2 or FastSCNN**, trained/fine-tuned on **RUGD + RELLIS-3D**, output collapsed to **4–6 navigability classes** (Free/Smooth, Rough-traversable, Obstacle, Forbidden/hazard), following the OFFSEG / Cross-Scale-Decoder class scheme.
- Obstacle detector: **YOLOv8n/YOLOv11n**, COCO-pretrained + fine-tuned on off-road obstacle crops (rocks, logs, people, other vehicles).
- Range-to-obstacle: run a lightweight monocular depth network (e.g., an MDE distilled/quantized network, or the Depth-Anything-small ONNX export) **asynchronously at 1–5 Hz**, sampled only at detected-obstacle bounding boxes — not a dense per-frame map, matching the Depth-Aware Rover pattern above.
- Output published as a ROS 2 topic: an occupancy-style grid (traversability) + a list of obstacle detections with estimated range/bearing.

**B. Visual SLAM/Odometry (Localization without GPS)**
- **ORB-SLAM3** in **stereo-inertial** mode (RealSense D435i or similar) as primary pose source.
- Fuse with **wheel odometry** via `robot_localization` EKF for robustness against textureless-scene tracking loss (a real risk outdoors — sky, dirt, grass are low-texture).
- Publish standard `nav_msgs/Odometry` + TF (`map → odom → base_link`), which is exactly the Nav2 input contract — no glue code needed beyond the existing ROS 2 wrappers.

**C. Path Planner (Point A → Point B, collision-free)**
- **Nav2** global planner (A* or Smac Hybrid — Hybrid-A* handles non-holonomic/skid-steer kinematics better for rough terrain).
- **Nav2 local controller**: start with **DWB** (well-documented, tunable); **TEB** is worth A/B testing since it handles dynamic obstacles and kinematic constraints more gracefully — the benchmark repo above (`reactive_autonomous_nav`) gives you a ready harness to compare both empirically on your own platform.
- Custom **costmap layer** consumes the Perception AI's traversability grid + obstacle list, mirroring the RGBD→YOLO→pointcloud→costmap-layer pattern from arXiv 2407.18535 — this is the cleanest, least-invasive way to get vision into Nav2.
- **Nav2 Collision Monitor** as an independent safety net (runs outside the main planner loop) to hard-stop on imminent collision regardless of planner state.

### 4.3 Why this design (traceable to research)

- **4–6 class segmentation, not full semantic segmentation** → OFFSEG's motivating argument and its 86.6%/80.2% mIoU results.
- **Navigability-grouped attention over raw class accuracy** → GANav's on-robot results showing +10% success rate and −37.8% forbidden-region false positives came from *navigability grouping*, not finer-grained segmentation.
- **Detector every frame, depth intermittently** → Depth-Aware Rover's explicit finding that dense per-frame monocular depth is infeasible on edge hardware, while a nano detector easily holds real-time.
- **Fuse VIO with wheel odometry** → literature explicitly flags that vision-only odometry can't give reliable global pose in real time; wheel+IMU+vision fusion is the standard mitigation.
- **Vision as a Nav2 costmap layer, not a new planner** → the arXiv 2407.18535 pipeline proves this integration path works without touching Nav2 internals, minimizing engineering risk.

---

## 5. Target Metrics / Numbers to Report

| Component | Metric | Literature benchmark | Your target |
|---|---|---|---|
| Terrain segmentation | mIoU (4–6 class) | 80–87% (OFFSEG on RELLIS-3D/RUGD) <cite index="13-1">86.61% on RELLIS-3D and 80.17% on RUGD using BiSeNetV2</cite> | ≥ 75% (fine-tuned, smaller dataset) |
| Terrain segmentation | Inference speed | Real-time on FastSCNN/BiSeNetV2 | ≥ 15–20 FPS on Jetson |
| Obstacle detection | Inference latency | 18–21 ms/frame (YOLOv8n, Jetson Orin Nano) <cite index="50-1">around twenty-one milliseconds average inference time at fifteen watts, improving to about eighteen milliseconds at higher power</cite> | ≤ 30 ms/frame |
| Obstacle detection | Effective range | ~15 m with monocular depth + detector fusion <cite index="38-1">enabling reliable obstacle avoidance within approximately fifteen meters using only a monocular camera</cite> | 5–10 m minimum for safe stop |
| Depth/height accuracy | RMSE | 0.048 m for 0.10–0.20 m obstacles (quadruped test) <cite index="34-1">an average RMSE of 0.048 meters for obstacle height estimation in that range</cite> | Order-of-magnitude reference only |
| Visual odometry | Drift | Validated against wheel-encoder ground truth on Jetson Nano <cite index="27-1">with wheel encoders providing ground truth for comparison against ORB-SLAM3 output</cite> | Report ATE/RPE vs. wheel odometry over test run |
| End-to-end navigation | Success rate improvement (adding navigability-aware perception) | +10% success rate, −37.8% forbidden-region false positives, −4.6–13.9% trajectory roughness (GANav on real Jackal/Husky) <cite index="59-1">with an increase in success rate, better surface selection, decreased trajectory roughness, and reduced forbidden-region false positive rate once integrated with the navigation algorithm on real robots</cite> | Report before/after A-to-B trials with and without perception-informed costmap |
| Control loop | Frequency | 50 Hz reactive control loop demonstrated on constrained hardware <cite index="31-1">using a fifty-hertz ROS-integrated control loop for smooth motion planning</cite> | ≥ 10 Hz cmd_vel minimum, 20–50 Hz preferred |

---

## 6. Implementation Plan (suggested sprints)

1. **Simulation-first (Week 1–2):** Stand up Gazebo world with off-road-like terrain; bring up a skid-steer/diff-drive UGV URDF + Nav2 + SLAM Toolbox (mirror `skunal3318/MapperBot-ROS2` / `RoverTech-team/Nav2` structure) to validate the full ROS 2 plumbing before touching real perception models.
2. **Perception module (Week 2–4):** Fine-tune BiSeNetV2/FastSCNN on RUGD+RELLIS-3D (4–6 class scheme); fine-tune YOLOv8n on off-road obstacle classes; wire up async lightweight-depth-at-bbox. Export all models to TensorRT/ONNX for the target board.
3. **Localization module (Week 3–5):** Bring up ORB-SLAM3 stereo-inertial via one of the ROS 2 wrapper repos; add `robot_localization` EKF fusing wheel odom + VIO; validate against wheel-encoder ground truth in a controlled loop-closure test.
4. **Costmap fusion + planner tuning (Week 4–6):** Implement the custom Nav2 costmap layer consuming perception outputs (mirror arXiv 2407.18535's pipeline); A/B test DWB vs TEB local controllers using the benchmark harness pattern from `reactive_autonomous_nav`.
5. **Hardware integration + field trials (Week 6–8):** Deploy on real UGV chassis + Jetson; run structured Point-A→B trials across at least 3 terrain types; log success rate, collisions, trajectory roughness, localization drift (ATE vs wheel odom) as your success-criteria evidence.
6. **Safety hardening:** Nav2 Collision Monitor as an independent watchdog; hard e-stop on perception/localization failure (e.g., SLAM tracking lost → fallback to wheel-odom-only + conservative speed cap).

---

## 7. Tech Stack Summary

| Layer | Choice | Rationale |
|---|---|---|
| Middleware | ROS 2 (Humble/Jazzy) | Industry standard, all reference repos target it |
| Compute | NVIDIA Jetson Orin Nano | ~18–21 ms YOLOv8n inference, TensorRT support, enough headroom for concurrent segmentation + SLAM |
| Camera | Stereo/RGB-D with IMU (e.g., Intel RealSense D435i or ZED 2i) | Needed for stereo-inertial ORB-SLAM3 and metric depth |
| Terrain segmentation | BiSeNetV2 / FastSCNN | Real-time-capable, proven 80–87% mIoU on RUGD/RELLIS-3D |
| Obstacle detection | YOLOv8n / YOLOv11n (Ultralytics) | De facto standard nano detector, native edge export |
| Depth (obstacles only) | Lightweight/quantized MDE, run async at low Hz | Dense per-frame MDE not real-time on edge; async pattern is proven |
| Localization | ORB-SLAM3 (stereo-inertial) + wheel odom via `robot_localization` EKF | Most accurate/robust open VSLAM system; fusion mitigates drift/tracking loss |
| Global/local planning | Nav2 (A*/Smac Hybrid + DWB/TEB) | Mature, don't reinvent; supports outdoor scenarios natively |
| Safety | Nav2 Collision Monitor | Independent of main planning loop |
| Simulation | Gazebo (+ ROS 2 bridges) | Validate pipeline before hardware risk |

---

## 8. References

1. Wigness, M., Eum, S., Rogers, J. G., Han, D., & Kwon, H. (2019). *A RUGD Dataset for Autonomous Navigation and Visual Perception in Unstructured Outdoor Environments.* IROS 2019.
2. Jiang, P., Osteen, P., Wigness, M., & Saripalli, S. (2020). *RELLIS-3D Dataset: Data, Benchmarks and Analysis.* arXiv:2011.12954.
3. Viswanath, K. et al. (2021). *OFFSEG: A Semantic Segmentation Framework For Off-Road Driving.* arXiv:2103.12417.
4. Guan, T., Kothandaraman, D., Chandra, R., Sathyamoorthy, A. J., Weerakoon, K., & Manocha, D. (2022). *GANav: Efficient Terrain Segmentation for Robot Navigation in Unstructured Outdoor Environments.* IEEE RA-L / arXiv:2103.04233. Code: github.com/rayguan97/GANav-offroad.
5. Cross-Scale Decoder with Token Refinement for Off-Road Semantic Segmentation. arXiv:2603.27931.
6. Frey, J. et al. (2024). *RoadRunner — Learning Traversability Estimation for Autonomous Off-road Driving.* arXiv:2402.19341.
7. Min, C. et al. *ORFD: A Dataset and Benchmark for Off-Road Freespace Detection.*
8. Vision-based Perception for Autonomous Vehicles in Obstacle Avoidance Scenarios (YOLOv11 + Depth Anything V2). arXiv:2507.12449.
9. Depth-Aware Rover: A Study of Edge AI and Monocular Vision for Real-World Implementation. arXiv:2604.22331.
10. Towards Real-Time Monocular Depth Estimation for Robotics: A Survey. arXiv:2111.08600.
11. Real-Time Monocular Human Depth Estimation and Segmentation on Embedded Systems. arXiv:2108.10506.
12. Monocular Vision-Based Obstacle Height Estimation for Mobile Robot. Applied Sciences (2025), doi:10.3390/app152312711.
13. Real-time vision-based obstacle avoidance for mobile robots using lightweight monocular depth estimation and behavior-driven control. J. Braz. Soc. Mech. Sci. Eng. (2025), doi:10.1007/s40430-025-06053-3.
14. Campos, C., Elvira, R., Gómez, J. J., Montiel, J. M. M., & Tardós, J. D. (2021). *ORB-SLAM3: An Accurate Open-Source Library for Visual, Visual-Inertial and Multi-Map SLAM.* IEEE Transactions on Robotics, 37(6), 1874–1890. Code: github.com/UZ-SLAMLab/ORB_SLAM3.
15. Implementation of Visual Odometry on Jetson Nano. Sensors 25(4), 1025 (2025), doi:10.3390/s25041025.
16. Improving the ROS 2 Navigation Stack with Real-Time Local Costmap (RGB-D + YOLOv8 → Nav2 costmap layer). arXiv:2407.18535.
17. Nav2 Documentation, ROS Navigation Working Group. github.com/ros-navigation/navigation2.
18. e-con Systems. *YOLOv8n benchmark on NVIDIA Jetson Orin Nano* (JetPack 5.1.2 vs 6.1). e-consystems.com/blog.
19. GitHub reference implementations (accessed Sept 2026):
    - `RoverTech-team/Nav2` — full skid-steer rover Nav2 stack with ZED 2i stereo perception.
    - `Robo-Friends-Tech/ROS2_ORB-SLAM3_Odometry` — ROS 2 ORB-SLAM3 odometry wrapper.
    - `Mechazo11/ros2_orb_slam3`, `gjcliff/ORB_SLAM3_ROS2` — alternative ROS 2 Humble ORB-SLAM3 wrappers.
    - `abdu7rahman/reactive_autonomous_nav` — pluggable global/local planner benchmark suite.
    - `skunal3318/MapperBot-ROS2` — minimal end-to-end Nav2 pipeline reference.
    - `rayguan97/GANav-offroad` — official GANav implementation.
    - `ultralytics/ultralytics` — YOLOv8/v11/v12 reference implementation and edge export tooling.

---

*Compiled from literature and open-source repository review, September 2026. Cited numeric results are as reported by the respective papers/benchmarks; independent verification on the target hardware/dataset is recommended before quoting them in a final submission.*
