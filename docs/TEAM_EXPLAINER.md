# DRISHTI-Nav — Team Explainer (read this before you open the PPT)

*For Team HACKTIDE. Plain-language guide to our backup problem statement PS 26126 (BEL), what we are building, why, and what every slide and every technology means. Written 28 Sep 2026.*

---

## 1. The problem statement in plain words

**Who gave it:** Bharat Electronics Limited (BEL), a defence electronics company. Category: Software. Theme: Smart Automation.

**What they want:** software that lets a small ground robot (a UGV, "unmanned ground vehicle", think of a rugged four-wheel rover) drive itself outdoors from a start point A to a destination point B **using only cameras**, **without GPS**, and **without hitting anything**.

**Why that is hard:**

- Outdoors there is no clean road. There is grass, dirt, gravel, mud, rocks, trees, ditches. Some of these you can drive over, some you cannot, and some you *can* but *should not* (mud will get you stuck).
- GPS is not available. Under trees, in valleys, or when a signal is jammed (a military situation), the robot does not know where it is. It has to figure out its own position by watching how the world moves in the camera as it drives. That is called **visual odometry** or **visual SLAM**.
- Lighting changes. Bright sun, deep shadows, dusk. A camera-based system that works at noon may see garbage at 6 pm. BEL explicitly says the system must handle this.
- Things appear suddenly. A rock, a person, an animal, a fallen branch. The robot must notice and go around without stopping the mission.

**BEL asks for three software pieces:**

| BEL's words | Plain meaning |
|---|---|
| Perception AI | A neural network that looks at the camera image and says which parts are safe ground and which parts are obstacles |
| Visual SLAM / odometry | Code that tracks where the robot is and which way it faces, from the camera alone |
| Path planner | Code that decides where to drive, and turns that into steering and speed commands |

**Success criterion:** the robot reaches B without a collision.

**Important for us:** it is a *software* problem statement. We do not have to build a robot. Our prototype is a simulation: a virtual robot with a virtual camera in a virtual field. A physical robot is "future work" on the slides.

---

## 2. Our situation

- We are at level 2 of SIH 2026. Our main statement (PS 26092, YojanaMitra) is already submitted.
- PS 26126 is our **backup**. The 6-slide deck was due 29 Sep 2026.
- What exists right now, all inside the `SIH-126` folder:
  - `deliverables/SIH_HACKTIDE_PS_26126.pptx` and `.pdf`: the 6 slides, same look as our YojanaMitra deck.
  - `deliverables/DRISHTI-Nav_demo.mp4`: a video of our prototype driving A to B, with a sudden rock, an unknown object, and a lighting drop.
  - `code/`: the Python code that produced that video. It runs on a laptop with no special software.
  - `docs/SOLUTION_GUIDE.md`: the long technical plan (architecture, stack, 10-week plan, datasets, demo script, team split). Read it after this file.
- Still to do by hand: upload the video to YouTube and paste the link on slides 3 and 6; push the folder to GitHub and paste the link on slide 6; confirm the Team ID on slide 1.

---

## 3. Our idea, in one paragraph

Every team will do the obvious thing: camera → object detector (YOLO) → SLAM → shortest path (A*) → drive. That treats the world as **free** or **blocked** and drives the shortest free path at full speed. It fails in three ways: it happily drives through mud because mud is "not an obstacle", it treats anything it cannot recognise as "free", and it drives at the same speed in bright sun and in deep shadow.

**DRISHTI-Nav** ("drishti" = vision in Sanskrit) replaces "free or blocked" with a **risk score from 0 to 100 for every patch of ground**, adds a **measure of how much the robot trusts its own camera right now**, and makes the robot **slow down and keep more distance when that trust drops**. It replans **only when something on its path actually changes**, not every frame.

**The analogy to use with judges:** a good human driver does not just avoid obstacles. They avoid the muddy shoulder, they slow down when the windscreen fogs up, and they give extra space to something they cannot identify on the road. We give the robot those three instincts.

---

## 4. The seven modules, and what each one actually does

The system is a loop that runs about ten times per second. Each module has an input, a job, and an output. "Prototype today" is what the Python code in `code/` does; "real build" is what we will build with ROS 2 and Gazebo over the next weeks.

### Module 1 — UGV and sensors
- **Input:** nothing; this is the world.
- **Job:** a four-wheel rover with a forward camera that gives colour + depth (an RGB-D camera, like an Intel RealSense; on a real robot depth comes from the camera hardware, we do not compute it), plus wheel odometry (how far the wheels turned). **No GPS.**
- **Output:** camera frames, wheel odometry.
- **Prototype today:** an 80 m × 80 m grid world with grass, dirt, gravel, a mud belt, rocks, a tree line, a ditch, and a sun whose brightness we can change. The camera view is rendered with simple perspective drawing. Obstacles can be spawned mid-run.
- **Real build:** Gazebo Harmonic (a robotics simulator) world, robot model, simulated RGB-D camera.

### Module 2 — Perception with uncertainty
- **Input:** one camera frame.
- **Job:** three things at once.
  1. **Segmentation**: label every pixel as one of 8 classes: grass, dirt, gravel, mud, rock, tree, ditch, novel. ("Novel" means "a thing that looks like nothing I was trained on".)
  2. **Unknown score per pixel**: instead of forcing a label, measure how badly *all* labels fit. We use the **energy score** (a number computed from the network's raw outputs; when no class fits, the energy is high). High energy → pixel is marked UNKNOWN (magenta on the dashboard).
  3. **Frame confidence C** (0 to 1): how good is this frame overall? Computed from image statistics (brightness, contrast, how many pixels are too dark, how much of the ground is in shadow) and from the network's own certainty. In the real build this is a small learned regressor trained in the simulator, where we know the true answer for every frame.
- **Output:** label image, unknown image, one confidence number.
- **Prototype today:** the neural network is a **stand-in**: it produces labels with noise that grows when the rendered image is dark or low-contrast. The energy score and confidence are computed for real from those outputs. Be honest about this if asked.
- **Real build:** SegFormer-B0 or Fast-SCNN (tiny segmentation networks, ~1–4 million parameters, real-time on a laptop CPU or a Jetson), trained on frames the simulator labels automatically, then fine-tuned on public off-road datasets (RUGD, RELLIS-3D, ORFD).

### Module 3 — Localisation
- **Input:** camera frames + wheel odometry.
- **Job:** estimate where the robot is and which way it faces, with no GPS. Visual odometry watches how image features move between frames and integrates that motion. Wheel odometry is fused in so that when the camera loses track (open grass, sky), the robot still has an estimate. It also reports a **tracking health H**: how many features it is tracking, and whether it is lost.
- **Output:** pose (x, y, heading), health H.
- **Prototype today:** a stand-in that integrates the true motion with drift that grows when few features are in view. We report the error against ground truth (ATE, about 0.3 m over a 100 m run).
- **Real build:** RTAB-Map (open-source RGB-D SLAM, installs with one command on ROS 2) fused with wheel odometry using the `robot_localization` EKF package. Ground-truth pose from the simulator is used *only* to compute error, never for driving.

### Module 4 — Risk map + event manager
- **Input:** labels, unknown scores, confidence (from 2); pose (from 3); depth.
- **Job:** the heart of the system.
  - Project every labelled pixel into a top-down grid (0.25 m cells in the real build, 0.5 m in the prototype) using the pose and depth.
  - Each cell remembers: which terrain class it probably is, obstacle probability, unknown score, how confident the camera was when it saw it, and when it was last seen. These update every frame; evidence accumulates, so a single noisy frame cannot create a fake obstacle.
  - Each cell gets **risk 0–100**: grass 10, dirt 22, gravel 38, mud 78, rock 97, tree 99, ditch 100; unknown adds 60 + 50 × unknown score; risk ≥ 90 is "lethal" (never drive through). Cells never seen get 35 ("uncertain", not "free"). When confidence is low, risk is pulled upward.
  - **Event manager:** it remembers the risk along the planned path at the moment the path was planned. Every frame it compares. If a cell on the upcoming path became lethal (E1), or the average risk rose a lot (E2), or the confidence band changed so the cost function changed (E3), or the robot has been stuck for 2 s (E4), it fires an event that triggers a global replan. Otherwise nothing is replanned. This is "event-driven replanning".
- **Output:** the risk grid, and events.
- **Prototype today:** fully real code.

### Module 5 — Behaviour governor
- **Input:** confidence C (from 2), health H (from 3).
- **Job:** pick a **band** and set the knobs for planner and controller.

| Band | When | Max speed | Safety margin | Risk weight λ | Ground it will drive locally |
|---|---|---|---|---|---|
| NORMAL | C ≥ 0.75 | 1.6 m/s | 0.5 m | 6 | risk < 85 |
| CAUTIOUS | 0.50–0.75 | 1.0 m/s | 1.0 m | 9 | risk < 76 |
| CONSERVATIVE | < 0.50 | 0.5 m/s | 1.0 m | 14 | risk < 66 |
| RECOVER | H lost | 0.25 m/s | 1.0 m | 14 | hold and re-acquire |

  Hysteresis means it does not flicker between bands when C hovers at a boundary.
- **Output:** the knob values.
- **Prototype today:** fully real.

### Module 6 — Adaptive planner
- **Input:** risk grid, pose, goal, knobs from the governor.
- **Job:** two planners.
  - **Global:** A* (a classic shortest-path search) over the grid, but each cell's cost is `1 + λ × (risk/100)²`, so a muddy cell costs several times a grass cell and the path bends around it. Runs only when an event fires; takes about 30 ms.
  - **Local:** every 0.1 s, sample 52 short arcs (combinations of speed and turn rate), roll each one forward 2 s over the risk grid, throw out any that touch a forbidden cell, and score the rest on risk, closeness to the global path, and progress. Pick the best.
  - It also computes the plain shortest path for display, so the dashboard shows "shortest route" vs "risk-aware route".
- **Output:** global path, chosen local arc.
- **Prototype today:** fully real.

### Module 7 — Controller
- **Input:** chosen arc, speed cap from the governor.
- **Job:** turn the arc into a velocity command (`/cmd_vel` in ROS terms: forward speed and turn rate), cap the speed, and hard-stop if a lethal cell is within 0.5 m.
- **Output:** the robot moves. A new frame arrives. Back to module 1.

---

## 5. Which technology does what, and who needs to learn it

| Technology | What it is | What we use it for | Learn it if you own |
|---|---|---|---|
| **Python + NumPy + SciPy** | The language and maths libraries everything is written in | The whole prototype; the risk map and planner stay in Python in the real build | everyone |
| **scikit-image** | Image library | Its `route_through_array` is a fast minimum-cost path finder; that is our A* | planner |
| **Matplotlib + imageio** | Plotting and video writing | The dashboard and the demo video | dashboard |
| **ROS 2 Jazzy** | Robot Operating System: a way to split a robot's software into "nodes" that pass messages on "topics" (like `/camera/rgb`, `/cmd_vel`) | Each module becomes a node; lets us swap the simulator for a real camera without changing code | simulation, integration |
| **Gazebo Harmonic** | 3-D physics simulator that plugs into ROS 2 | The outdoor world, the robot, the camera. Its **segmentation camera** gives us perfectly labelled training images for free | simulation |
| **PyTorch** | Deep learning library | Training the segmentation network | perception |
| **SegFormer-B0 / Fast-SCNN** | Small, fast segmentation networks | The "Perception AI" BEL asks for | perception |
| **ONNX Runtime / TensorRT** | Ways to run a trained network fast on CPU or on an NVIDIA Jetson | Proving the model is "lightweight" | perception |
| **RTAB-Map** | Open-source RGB-D SLAM | The "Visual SLAM" BEL asks for | localisation |
| **robot_localization (EKF)** | ROS 2 package that fuses several motion estimates | Combining visual odometry with wheel odometry | localisation |
| **Foxglove Studio** | A viewer for ROS 2 topics | Quick dashboards during development | dashboard |
| **FastAPI + WebSocket** | Lightweight Python web server | The judge-facing web dashboard | dashboard |
| **RUGD, RELLIS-3D, ORFD** | Public off-road image datasets with labels | Fine-tuning on real images; ORFD has day/dusk/dark variation | data |
| **Ubuntu 24.04** | Linux | ROS 2 and Gazebo only run on Linux. At least one laptop must have it | simulation |

**Fallback if Gazebo fights us:** Webots, a simulator that runs on macOS with a Python API and no ROS. Same module interfaces.

---

## 6. Slide-by-slide: what it says and what to say

### Slide 1 — Title
PS ID 26126, title, theme Smart Automation, category Software, Team ID 137858, team HACKTIDE. Nothing to explain. Check the Team ID.

### Slide 2 — The idea
- **Top strip "End-to-end autonomy loop":** the six verbs Perceive → Assess → Localise → Map → Plan → Move. This is the seven modules above compressed to six icons (governor + controller are "Move").
- **"Existing approach vs DRISHTI-Nav":** left column is what every other team will do; right column is our answer to each line. Memorise the pairs: binary map → risk field; shortest path → safer route; "not detected = safe" → "unknown = uncertain = avoid"; blind to lighting → confidence-aware speed; replan every frame → replan on events; no self-trust → localisation health.
- **"Innovation & uniqueness":** our five claims. If asked "what is new", say these five.
- **"Safety by design":** the fail-safes. Unseen ground is never assumed free; hard stop near lethal cells; low confidence → slow; SLAM lost → hold; evidence accumulates so noise does not stop the robot; camera-only, no GPS.

### Slide 3 — Flow and architecture
Numbered boxes 1–7 are exactly the seven modules in Section 4, in data-flow order. Read it like this: sensors (1) feed perception (2) and localisation (3) **at the same time**; both feed the risk map (4); confidence and health go along the dashed amber line into the governor (5); the governor sets knobs on the planner (6) and controller (7); the controller moves the robot and the blue loop at the bottom brings a new frame back to (1).

The bottom strip "What happens when the world changes" is the demo storyline: rock appears → detected in one frame → replan in ~30 ms; unfamiliar object → marked UNKNOWN → avoided with a wider berth; sun dims → confidence 0.95 → 0.47 → CONSERVATIVE band → speed 1.6 → 0.5 m/s; light returns → NORMAL → goal reached.

### Slide 4 — Tech stack and feasibility
Six technology cards (Section 5). "Why this is buildable": no manual labelling (the simulator labels for us), everything is grid maths, same code runs on a Jetson, and a prototype already exists. Right side: four risks and four mitigations, one to one:

| Risk | Mitigation |
|---|---|
| SLAM loses tracking on grass/sky | fuse with wheel odometry; health signal → hold and re-acquire |
| Segmentation degrades in shadow/dusk | governor slows and widens margins; CLAHE (a contrast-boosting image filter) when dark |
| Unseen objects called "safe" | energy-score unknown detection + a "novel" class trained by putting random junk objects in the simulator |
| Simulator looks different from reality | randomise sun, textures, fog in sim; fine-tune on real datasets |

### Slide 5 — Impact and benefits
Who benefits: defence UGVs in GPS-denied areas (BEL's own use case), search and rescue, agriculture, delivery/surveillance/mining. The six "key program impacts" quote our prototype numbers. Target audience and "who gains what" mirror the YojanaMitra deck's structure.

### Slide 6 — Research, references, links, results
- Screenshot of the prototype dashboard at the moment the unknown object is detected.
- Results table: 15 seeded runs per planner (45 total), same world, same events.

| Metric | Binary planner (the standard approach) | DRISHTI-Nav |
|---|---|---|
| Success, no collision | 100 % | 100 % |
| Time driving in mud per run | 39.7 s | 0.6 s |
| Hazard detection latency | 960 ms | 213 ms |
| Global replans per run | 43 | 23 |
| Path length | 94 m | 106 m |

  How to read it: in this world both planners reach B, so our win is not "fewer crashes" but **safer ground** (40 s of mud → under 1 s), **faster reaction** (about 1 s → about 2 frames), and **fewer wasted replans**, at the cost of a 13 % longer path. That trade is the whole point: safer, not shorter.
- The middle column "Risk-aware" is our system with the governor switched off; it shows that the risk map alone fixes the mud problem, and the governor adds the lighting behaviour.
- 14 references: datasets, the papers behind energy-score unknown detection, SLAM, planners.

---

## 7. The prototype: run it, and what you will see

```bash
pip install numpy scipy scikit-image matplotlib imageio imageio-ffmpeg
cd SIH-126/code
python run_demo.py --seed 5 --every 3          # ~10 minutes, writes output/demo_full.mp4 and PNG snapshots
python run_eval.py --runs 15                  # ~20 minutes, writes output/results.csv and output/summary.md
```

**The dashboard (what the video shows):**
- **Top left:** the simulated camera. Brown = mud, grey = gravel/rocks, dark green = trees, black = ditch, purple block = the unknown object.
- **Bottom left:** what perception thinks. Same colours, plus magenta = UNKNOWN.
- **Right:** the risk map from above. Green = safe, yellow/orange = risky, red = lethal, grey = never seen, magenta = unknown. White line = our route. Grey dashed = the shortest route (through the mud). Yellow triangle = the robot. Blue line = where the robot *thinks* it is; black dotted = where it really is.
- **Bottom:** confidence gauge, localisation health, current band, speed, event log.

**The scripted events:** at 14 s a rock is dropped 7 m ahead on the path; at 30 s an unknown purple object; at 46 s the sun dims to 15 %; at 70 s it comes back.

**Files in `code/drishti_nav/`:** `world.py` (terrain + risk table), `sensor.py` (camera renderer + perception stand-in), `localization.py` (odometry stand-in), `risk_map.py` (module 4), `planner.py` (modules 5, 6, and the event manager), `sim.py` (the loop + module 7 + metrics), `viz.py` (dashboard).

---

## 8. Glossary

- **UGV** — unmanned ground vehicle. A driverless land robot.
- **GPS-denied** — no satellite positioning available.
- **RGB-D camera** — a camera that gives colour and a depth (distance) value per pixel. RealSense, ZED.
- **Segmentation** — labelling every pixel of an image with a class.
- **Visual odometry (VO)** — estimating motion from how the camera image changes frame to frame.
- **SLAM** — Simultaneous Localisation and Mapping: VO plus building a map and correcting drift when you revisit a place.
- **EKF** — Extended Kalman Filter; a standard way to fuse several noisy estimates into one.
- **Costmap / risk map** — a top-down grid where each cell has a cost or risk for the planner.
- **A\*** — a classic algorithm that finds the cheapest path across a grid.
- **Local planner / arc sampling** — trying many short candidate motions and picking the best one, each fraction of a second.
- **Energy score** — a number from a network's raw outputs that is high when no class explains the input; used to flag "unknown".
- **OOD** — out-of-distribution: input that looks like nothing in the training data.
- **Confidence C** — our 0–1 estimate of how trustworthy the current camera frame is.
- **Inflation / safety margin** — extra distance kept from obstacles.
- **λ (lambda)** — how heavily the planner weighs risk against distance.
- **ATE** — average trajectory error, how far the estimated position is from the truth.
- **Seeded run** — a simulation run with a fixed random seed, so it can be repeated exactly.
- **Ablation** — removing one feature to measure what it contributes (our "risk-aware, no governor" column).
- **ROS 2 node / topic** — a process and the named message channel it publishes on.

---

## 9. Questions judges may ask, and the answers

- **Why cameras and not LiDAR?** The statement asks for camera-primary. Cameras are cheap and tell you *what* the ground is (mud vs grass), which LiDAR cannot. LiDAR could be added as one more layer of the risk map.
- **Where does depth come from?** From an RGB-D or stereo camera; the hardware computes it. We do not rely on monocular depth networks.
- **Is the perception real in the prototype?** No. The prototype uses a stand-in whose noise depends on the rendered image. The risk map, event manager, planner, governor, and evaluation are real code. Training the real network is the next phase; the simulator gives us labelled data for free.
- **What if it is night?** Confidence drops, the governor goes conservative, and below a floor the robot stops. We do not claim night driving.
- **What if SLAM fails?** Health drops → speed capped → wheel odometry carries it → after a timeout it stops and rotates to re-acquire features.
- **Why is the full system one frame slower at detecting hazards than the "risk-aware only" version?** Because it weights evidence by confidence, so it needs slightly more agreement before it commits. That is the price of not stopping for phantom obstacles in low light.
- **Where do the risk numbers (grass 10, mud 78) come from?** A configurable table we set by hand for now. Future work learns them from the robot's own experience (wheel slip, tilt), as ETH's Wild Visual Navigation does.
- **Will it run on a real robot?** The modules are ROS 2 nodes; swap the Gazebo camera topic for a real camera topic. The model is ~3.7 M parameters, sized for a Jetson.

---

## 10. What each teammate should do next

| Member | Own | First task | Read |
|---|---|---|---|
| Perception | segmentation network, unknown score, confidence regressor | Run the prototype, open `sensor.py`, understand what the stand-in outputs; then train a SegFormer-B0 on RUGD as a warm-up | Section 4 (module 2), SOLUTION_GUIDE §B2, §B3, §G |
| Localisation | RTAB-Map + EKF, health signal | Get RTAB-Map running on any ROS 2 bag | Section 4 (module 3), SOLUTION_GUIDE §E |
| Mapping & planning | risk map, events, A*, local planner, governor | Open `risk_map.py` and `planner.py`; change a risk value and watch the route change | Section 4 (modules 4–7), SOLUTION_GUIDE §B1, §B4 |
| Simulation | Gazebo world, robot, camera, scenario runner | Install Ubuntu 24.04 + ROS 2 Jazzy + Gazebo Harmonic; get a camera frame into a Python node | SOLUTION_GUIDE §E, §F |
| Dashboard & integration | Foxglove, web view, launch files | Open `viz.py`; reproduce the dashboard in Foxglove | SOLUTION_GUIDE §J interface table |
| Data, evaluation, docs | datasets, harness, metrics, PPT, video | Run `run_eval.py`; download RUGD, RELLIS-3D, ORFD | SOLUTION_GUIDE §G, §K |

The one milestone that matters: **a virtual robot driving A to B in Gazebo by the end of week 3**, even with perfect (ground-truth) labels and pose. Everything else is layered on top.
