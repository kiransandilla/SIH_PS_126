// Builds SIH_HACKTIDE_PS_26126.pptx in the HACKTIDE house style (6 slides).
// Usage: node build_deck.js
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");
const sharp = require("sharp");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const Fa = require("react-icons/fa");

const ASSETS = path.join(__dirname, "assets");
const PROTO = path.join(__dirname, "..", "code", "output");
const OUT = path.join(__dirname, "SIH_HACKTIDE_PS_26126.pptx");

// ---------------------------------------------------------------- palette
const NAVY = "1F3A93", INK = "1E2761", TEXT = "222222", MUTED = "555555";
const GREEN = "2E7D32", AMBER = "B26A00", RED = "C62828", PURPLE = "6A1B9A", TEAL = "00695C", BLUE = "1565C0";
const LIGHT = { blue: "EAF1FB", green: "EAF6EC", amber: "FFF4E0", red: "FDECEC", purple: "F1E8F7", teal: "E4F3F1", grey: "F3F4F6" };
const FONT_H = "Times New Roman", FONT = "Arial";

// ---------------------------------------------------------------- icons
async function icon(name, color, size = 256) {
  const El = Fa[name];
  if (!El) throw new Error("no icon " + name);
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(El, { color: "#" + color, size }));
  const buf = await sharp(Buffer.from(svg)).resize(size, size).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}
const ICONS = {};
async function loadIcons() {
  const spec = {
    eye: ["FaEye", "FFFFFF"], brain: ["FaBrain", "FFFFFF"], crosshair: ["FaCrosshairs", "FFFFFF"], map: ["FaMap", "FFFFFF"],
    route: ["FaRoute", "FFFFFF"], robot: ["FaRobot", "FFFFFF"], shield: ["FaShieldAlt", "FFFFFF"], check: ["FaCheckCircle", "43A047"],
    times: ["FaTimesCircle", "D32F2F"], camera: ["FaCamera", NAVY], bolt: ["FaBolt", AMBER], sun: ["FaSun", AMBER],
    question: ["FaQuestionCircle", PURPLE], layer: ["FaLayerGroup", TEAL], sync: ["FaSyncAlt", BLUE], chart: ["FaChartLine", GREEN],
    users: ["FaUsers", "FFFFFF"], bullseye: ["FaBullseye", "FFFFFF"], warn: ["FaExclamationTriangle", "FFFFFF"], search: ["FaSearch", "FFFFFF"],
    bulb: ["FaLightbulb", "FFFFFF"], code: ["FaCode", "FFFFFF"], video: ["FaVideo", RED], github: ["FaGithub", INK], book: ["FaBook", "FFFFFF"],
    tractor: ["FaTractor", GREEN], ambulance: ["FaAmbulance", RED], truck: ["FaTruck", BLUE], satellite: ["FaSatelliteDish", PURPLE],
    plane: ["FaFighterJet", NAVY], mountain: ["FaMountain", AMBER], gauge: ["FaTachometerAlt", TEAL], cube: ["FaCube", BLUE],
    cog: ["FaCogs", NAVY], flag: ["FaFlagCheckered", GREEN], cloudsun: ["FaCloudSun", AMBER], microchip: ["FaMicrochip", TEAL],
  };
  for (const [k, [n, c]] of Object.entries(spec)) ICONS[k] = await icon(n, c);
}

// ---------------------------------------------------------------- helpers
function chrome(pres, slide, num, title) {
  slide.background = { color: "FFFFFF" };
  // team oval (top-left) as in the original deck
  slide.addShape(pres.ShapeType.ellipse, { x: 0.15, y: 0.08, w: 1.05, h: 0.62, line: { color: "7A7FBF", width: 1 }, fill: { color: "FFFFFF" } });
  slide.addText("HACKTIDE", { x: 0.15, y: 0.08, w: 1.05, h: 0.62, fontFace: FONT, fontSize: 10, color: TEXT, align: "center", valign: "middle", margin: 0, isTextBox: true });
  slide.addImage({ path: path.join(ASSETS, "p1_img505.png"), x: 8.15, y: 0.06, w: 1.72, h: 0.82 });
  if (title) slide.addText(title, { x: 1.4, y: 0.12, w: 6.6, h: 0.6, fontFace: FONT_H, fontSize: 24, bold: true, color: NAVY, align: "center", valign: "middle", margin: 0, isTextBox: true });
  // footer band (house style of the submitted deck)
  slide.addShape(pres.ShapeType.rect, { x: 0, y: 5.28, w: 10, h: 0.345, fill: { color: NAVY }, line: { color: NAVY } });
  slide.addText(String(num), { x: 9.3, y: 5.3, w: 0.5, h: 0.3, fontFace: FONT, fontSize: 11, bold: true, color: "FFFFFF", align: "right", margin: 0, isTextBox: true });
}
function sectionBar(pres, slide, text, x, y, w, color = NAVY) {
  slide.addShape(pres.ShapeType.roundRect, { x, y, w, h: 0.26, fill: { color }, line: { color }, rectRadius: 0.04 });
  slide.addText(text, { x: x + 0.1, y, w: w - 0.15, h: 0.26, fontFace: FONT, fontSize: 9, bold: true, color: "FFFFFF", valign: "middle", margin: 0, isTextBox: true });
}
function card(pres, slide, x, y, w, h, fill, line = "D9DCE3") {
  slide.addShape(pres.ShapeType.roundRect, { x, y, w, h, fill: { color: fill }, line: { color: line, width: 0.75 }, rectRadius: 0.05 });
}
function iconCircle(pres, slide, key, x, y, d, color) {
  slide.addShape(pres.ShapeType.ellipse, { x, y, w: d, h: d, fill: { color }, line: { color } });
  slide.addImage({ data: ICONS[key], x: x + d * 0.24, y: y + d * 0.24, w: d * 0.52, h: d * 0.52 });
}
function txt(slide, text, x, y, w, h, o = {}) {
  slide.addText(text, Object.assign({ x, y, w, h, fontFace: FONT, fontSize: 9, color: TEXT, margin: 0, isTextBox: true, valign: "top" }, o));
}
function rich(parts) { return parts.map(p => (typeof p === "string" ? { text: p } : p)); }

// ---------------------------------------------------------------- metrics
function readMetrics() {
  const f = path.join(PROTO, "results.csv");
  const m = { baseline: {}, risk_only: {}, full: {} };
  if (!fs.existsSync(f)) return null;
  const rows = fs.readFileSync(f, "utf8").trim().split("\n").map(l => l.split(","));
  const head = rows.shift();
  const idx = k => head.indexOf(k);
  const by = {};
  for (const r of rows) (by[r[idx("mode")]] = by[r[idx("mode")]] || []).push(r);
  for (const mode of Object.keys(by)) {
    const rs = by[mode], n = rs.length;
    const mean = k => rs.reduce((a, r) => a + parseFloat(r[idx(k)] || 0), 0) / n;
    m[mode] = {
      n, success: Math.round(100 * rs.filter(r => r[idx("success")] === "True").length / n),
      collided: rs.filter(r => r[idx("collided")] === "True").length,
      mud: (mean("mud_steps") * 0.1).toFixed(1), path: mean("path_len").toFixed(1), time: Math.round(mean("time_s")),
      replans: mean("replans").toFixed(1), replan_ms: Math.round(mean("replan_ms")), ate: mean("ate_m").toFixed(2),
      detect: Math.round(rs.filter(r => r[idx("detect_ms")] && r[idx("detect_ms")] !== "None").reduce((a, r) => a + parseFloat(r[idx("detect_ms")]), 0) / Math.max(1, rs.filter(r => r[idx("detect_ms")] && r[idx("detect_ms")] !== "None").length)),
    };
  }
  return m;
}

// ================================================================= build
(async () => {
  await loadIcons();
  const M = readMetrics();
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.author = "Team HACKTIDE";
  pres.title = "SIH 2026 - PS 26126 - DRISHTI-Nav";

  // ---------------------------------------------------------- slide 1
  {
    const s = pres.addSlide();
    s.background = { color: "FFFFFF" };
    s.addImage({ path: path.join(ASSETS, "p1_img505.png"), x: 8.0, y: 0.1, w: 1.85, h: 0.88 });
    s.addText("SMART INDIA HACKATHON 2026", { x: 0.6, y: 0.45, w: 7.2, h: 0.7, fontFace: FONT_H, fontSize: 30, bold: true, color: NAVY, align: "center", valign: "middle", margin: 0, isTextBox: true });
    s.addImage({ path: path.join(ASSETS, "p1_img25.png"), x: 6.15, y: 1.35, w: 3.2, h: 3.42 });
    const rows = [
      ["PROBLEM STATEMENT ID - ", "26126"],
      ["PROBLEM STATEMENT TITLE - ", "VISION BASED AUTONOMOUS NAVIGATION FOR UNMANNED GROUND VEHICLE FOR OUTDOOR ENVIRONMENT"],
      ["THEME - ", "Smart Automation"],
      ["PS Category - ", "Software"],
      ["Team ID - ", "137858"],
      ["TEAM NAME - ", "HACKTIDE"],
    ];
    let y = 1.45;
    for (const [k, v] of rows) {
      const h = k.startsWith("PROBLEM STATEMENT TITLE") ? 0.78 : 0.42;
      s.addText([{ text: "◦  ", options: { color: MUTED } }, { text: k, options: { bold: true } }, { text: v }],
        { x: 0.35, y, w: 5.9, h, fontFace: FONT, fontSize: 13, color: "000000", valign: "top", margin: 0, isTextBox: true });
      y += h + 0.1;
    }
    s.addNotes("Title slide. Backup problem statement for Team HACKTIDE (PS 26126, BEL).");
  }

  // ---------------------------------------------------------- slide 2
  {
    const s = pres.addSlide();
    chrome(pres, s, 2, null);
    s.addImage({ data: ICONS.eye, x: 3.55, y: 0.14, w: 0.36, h: 0.36 });
    s.addText("DRISHTI-Nav", { x: 3.9, y: 0.05, w: 3.0, h: 0.55, fontFace: FONT, fontSize: 26, bold: true, color: NAVY, valign: "middle", margin: 0, isTextBox: true });
    txt(s, "See  •  Assess  •  Adapt  —  camera-only navigation that knows how much to trust its own eyes", 1.3, 0.58, 6.7, 0.24, { fontSize: 9.5, bold: true, color: NAVY, align: "center" });
    txt(s, "One closed loop: perceive terrain, score risk and uncertainty, localise without GPS, replan on change, reach B safely.", 1.3, 0.82, 6.7, 0.22, { fontSize: 8, color: MUTED, align: "center" });

    // journey strip
    sectionBar(pres, s, "END-TO-END AUTONOMY LOOP", 0.25, 1.12, 9.5);
    card(pres, s, 0.25, 1.42, 9.5, 1.32, "F7F9FD");
    const steps = [
      ["eye", NAVY, "Perceive", "Lightweight segmentation labels grass, dirt, gravel, mud, rock, tree, ditch."],
      ["question", PURPLE, "Assess", "Energy score flags unknown pixels; a learned regressor rates frame confidence."],
      ["crosshair", TEAL, "Localise", "Visual odometry / SLAM + wheel odometry; tracking health monitored."],
      ["layer", AMBER, "Map", "Dynamic risk map 0–100 per cell: terrain, geometry, obstacle, unknown, staleness."],
      ["route", GREEN, "Plan", "Global A* on risk cost fires on events; local arc planner at 10 Hz."],
      ["robot", BLUE, "Move", "Governor sets speed and margins from confidence; controller drives the UGV."],
    ];
    steps.forEach(([ic, col, t, d], i) => {
      const x = 0.4 + i * 1.575;
      iconCircle(pres, s, ic, x + 0.45, 1.5, 0.5, col);
      s.addShape(pres.ShapeType.ellipse, { x: x + 0.82, y: 1.47, w: 0.17, h: 0.17, fill: { color: "FFFFFF" }, line: { color: col, width: 1 } });
      txt(s, String(i + 1), x + 0.82, 1.47, 0.17, 0.17, { fontSize: 7, bold: true, color: col, align: "center", valign: "middle" });
      txt(s, t, x, 2.04, 1.4, 0.2, { fontSize: 9.5, bold: true, color: col, align: "center" });
      txt(s, d, x, 2.24, 1.4, 0.48, { fontSize: 7, color: TEXT, align: "center" });
      if (i < 5) s.addShape(pres.ShapeType.line, { x: x + 1.05, y: 1.75, w: 0.42, h: 0, line: { color: "9AA3B5", width: 1, endArrowType: "triangle" } });
    });

    // existing vs ours
    sectionBar(pres, s, "EXISTING APPROACH VS DRISHTI-NAV", 0.25, 2.86, 3.95);
    card(pres, s, 0.25, 3.16, 1.9, 2.02, LIGHT.red, "F1B9B9");
    txt(s, "Existing Approach", 0.35, 3.2, 1.75, 0.22, { fontSize: 9, bold: true, color: RED });
    const bad = ["Binary free / blocked map", "Shortest path at full speed", "'Not detected' treated as safe", "Blind to lighting changes", "Full replan every frame", "No measure of self-trust"];
    bad.forEach((b, i) => { s.addImage({ data: ICONS.times, x: 0.35, y: 3.48 + i * 0.28, w: 0.13, h: 0.13 }); txt(s, b, 0.52, 3.45 + i * 0.28, 1.6, 0.26, { fontSize: 7.2, bold: true }); });
    s.addShape(pres.ShapeType.ellipse, { x: 2.18, y: 4.05, w: 0.24, h: 0.24, fill: { color: NAVY }, line: { color: NAVY } });
    txt(s, "→", 2.18, 4.05, 0.24, 0.24, { fontSize: 10, bold: true, color: "FFFFFF", align: "center", valign: "middle" });
    card(pres, s, 2.45, 3.16, 1.75, 2.02, LIGHT.green, "BFE3C5");
    txt(s, "DRISHTI-Nav", 2.55, 3.2, 1.6, 0.22, { fontSize: 9, bold: true, color: GREEN });
    const good = ["Continuous risk field (0–100)", "Safer route, not just shorter", "Unknown → uncertain → avoid", "Confidence-aware speed & margin", "Event-driven replanning", "Localisation health → recovery"];
    good.forEach((b, i) => { s.addImage({ data: ICONS.check, x: 2.55, y: 3.48 + i * 0.28, w: 0.13, h: 0.13 }); txt(s, b, 2.72, 3.45 + i * 0.28, 1.5, 0.26, { fontSize: 7.2, bold: true }); });

    // innovation & uniqueness
    sectionBar(pres, s, "INNOVATION & UNIQUENESS", 4.35, 2.86, 3.0);
    card(pres, s, 4.35, 3.16, 3.0, 2.02, "FFFFFF");
    const inn = [
      ["layer", "Multi-layer dynamic risk map", "Terrain + geometry + obstacle + unknown fused per cell, updated every frame."],
      ["question", "Unknown-aware perception", "Energy-score OOD + 'novel' class: unfamiliar objects get risk, not a free pass."],
      ["gauge", "Perception-confidence governor", "Learned frame-quality score drives speed, safety margin and risk weight."],
      ["bolt", "Event-driven replanning", "Global A* only when the path corridor changes; local arcs at 10 Hz."],
      ["sun", "Lighting-adaptive behaviour", "Shadows / low light → lower confidence → conservative navigation."],
    ];
    inn.forEach(([ic, t, d], i) => {
      const y = 3.22 + i * 0.395;
      s.addImage({ data: ICONS[ic], x: 4.45, y: y + 0.03, w: 0.2, h: 0.2 });
      txt(s, t, 4.72, y, 2.6, 0.18, { fontSize: 8, bold: true, color: NAVY });
      txt(s, d, 4.72, y + 0.16, 2.6, 0.24, { fontSize: 6.6, color: MUTED });
    });

    // safety by design
    sectionBar(pres, s, "SAFETY BY DESIGN", 7.5, 2.86, 2.25);
    card(pres, s, 7.5, 3.16, 2.25, 2.02, INK, INK);
    iconCircle(pres, s, "shield", 7.62, 3.26, 0.42, "2F4BB5");
    txt(s, "Fail-safe autonomy", 8.1, 3.27, 1.6, 0.2, { fontSize: 9, bold: true, color: "FFFFFF" });
    txt(s, "Every uncertainty has a response", 8.1, 3.46, 1.6, 0.2, { fontSize: 6.5, color: "C9D3F5" });
    const saf = ["Unseen cells carry risk, never 'free'", "Hard stop on lethal cell ahead", "Low confidence → slow + wide margin", "SLAM lost → hold, re-acquire", "Evidence accumulates, no phantom stops", "Works with RGB-D / stereo, no GPS"];
    saf.forEach((b, i) => { s.addImage({ data: ICONS.check, x: 7.62, y: 3.78 + i * 0.225, w: 0.12, h: 0.12 }); txt(s, b, 7.8, 3.75 + i * 0.225, 1.9, 0.22, { fontSize: 6.8, color: "FFFFFF" }); });
    s.addNotes("Idea slide: the loop, the contrast with the standard camera->YOLO->SLAM->A* chain, the five innovations and the safety posture.");
  }

  // ---------------------------------------------------------- slide 3
  {
    const s = pres.addSlide();
    chrome(pres, s, 3, "FLOW AND ARCHITECTURE");
    s.addImage({ data: ICONS.cog, x: 1.45, y: 0.2, w: 0.42, h: 0.42 });
    const box = (x, y, w, h, title, lines, col, fill, num) => {
      card(pres, s, x, y, w, h, fill, col);
      if (num !== undefined) { s.addShape(pres.ShapeType.ellipse, { x: x + 0.06, y: y + 0.06, w: 0.2, h: 0.2, fill: { color: col }, line: { color: col } }); txt(s, String(num), x + 0.06, y + 0.06, 0.2, 0.2, { fontSize: 7, bold: true, color: "FFFFFF", align: "center", valign: "middle" }); }
      txt(s, title, x + (num !== undefined ? 0.3 : 0.08), y + 0.05, w - 0.35, 0.22, { fontSize: 8.5, bold: true, color: col });
      txt(s, lines.map((l, i) => ({ text: l, options: { bullet: { indent: 8 }, breakLine: i < lines.length - 1 } })), x + 0.08, y + 0.28, w - 0.16, h - 0.32, { fontSize: 6.6, color: TEXT, paraSpaceAfter: 1 });
    };
    const arrow = (x1, y1, x2, y2, col = "3A4A6B") => {
      const flipH = x2 < x1, flipV = y2 < y1;
      s.addShape(pres.ShapeType.line, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1), flipH, flipV, line: { color: col, width: 1.25, endArrowType: "triangle" } });
    };
    // Data-flow layout: sensors feed perception AND localisation in parallel; both feed the risk map;
    // governor (fed by confidence + localisation health) parametrises planner and controller; loop closes.
    box(0.25, 0.95, 1.5, 2.15, "UGV & sensors", ["Gazebo Harmonic outdoor world", "RGB-D camera 640×480, 90° FOV", "Wheel odometry — no GPS", "Scenario runner: spawn obstacle, change sun"], NAVY, LIGHT.blue, 1);
    box(2.0, 0.95, 2.15, 1.05, "Perception with uncertainty", ["SegFormer-B0 / Fast-SCNN, 8 classes, ONNX", "Energy score → per-pixel UNKNOWN", "Frame confidence C (learned regressor)", "CLAHE pre-processing when dark"], PURPLE, LIGHT.purple, 2);
    box(2.0, 2.15, 2.15, 0.95, "Localisation", ["RTAB-Map RGB-D visual odometry", "EKF fusion with wheel odometry", "Tracking health H: features, inliers, lost"], TEAL, LIGHT.teal, 3);
    box(4.4, 0.95, 2.3, 2.15, "Risk map + events", ["Depth → points → 0.25 m cells; per cell: class belief, obstacle log-odds, height, unknown, confidence, last seen", "risk = max(terrain, geometry, obstacle, unknown), pulled toward 'uncertain' when C is low; unseen = 35", "Events: E1 new lethal cell on path · E2 corridor risk rise · E3 band change · E4 blocked > 2 s → replan"], RED, LIGHT.red, 4);
    box(6.95, 0.95, 2.8, 0.66, "Behaviour governor", ["C, H → band NORMAL / CAUTIOUS / CONSERVATIVE / RECOVER", "band → v_max, margin, risk weight λ, unknown weight"], AMBER, LIGHT.amber, 5);
    box(6.95, 1.75, 1.35, 1.35, "Adaptive planner", ["Global A* on 1 + λ·risk², events only (~30 ms)", "Local: 52 arcs, 2 s rollout, 10 Hz", "Shortest vs safest routes"], GREEN, LIGHT.green, 6);
    box(8.45, 1.75, 1.3, 1.35, "Controller", ["Pure pursuit on local arc", "Speed ≤ v_max(C)", "Hard stop if lethal < 0.5 m", "/cmd_vel → skid-steer"], BLUE, LIGHT.blue, 7);
    // sensors -> perception and localisation (parallel)
    arrow(1.75, 1.45, 2.0, 1.45, NAVY); arrow(1.75, 2.6, 2.0, 2.6, NAVY);
    // perception & localisation -> risk map
    arrow(4.15, 1.45, 4.4, 1.45, PURPLE); arrow(4.15, 2.6, 4.4, 2.6, TEAL);
    // risk map -> planner
    arrow(6.7, 2.4, 6.95, 2.4, RED);
    // planner -> controller
    arrow(8.3, 2.4, 8.45, 2.4, GREEN);
    // confidence C + health H -> governor (dashed, runs above the risk map box)
    s.addShape(pres.ShapeType.line, { x: 3.1, y: 0.78, w: 3.85, h: 0, line: { color: AMBER, width: 1.25, dashType: "dash", endArrowType: "triangle" } });
    s.addShape(pres.ShapeType.line, { x: 3.1, y: 0.78, w: 0, h: 0.17, line: { color: AMBER, width: 1.25, dashType: "dash" } });
    txt(s, "confidence C (from 2)  +  localisation health H (from 3)", 3.2, 0.6, 3.6, 0.18, { fontSize: 5.8, italic: true, color: AMBER });
    // governor -> planner and controller
    arrow(7.6, 1.61, 7.6, 1.75, AMBER); arrow(9.1, 1.61, 9.1, 1.75, AMBER);
    txt(s, "λ, margin", 7.66, 1.6, 0.6, 0.14, { fontSize: 5.2, italic: true, color: AMBER });
    txt(s, "v_max", 9.16, 1.6, 0.5, 0.14, { fontSize: 5.2, italic: true, color: AMBER });
    // loop back: controller -> UGV moves -> next frame
    s.addShape(pres.ShapeType.line, { x: 9.1, y: 3.1, w: 0, h: 0.3, line: { color: BLUE, width: 1.25 } });
    s.addShape(pres.ShapeType.line, { x: 1.0, y: 3.4, w: 8.1, h: 0, line: { color: BLUE, width: 1.25 } });
    s.addShape(pres.ShapeType.line, { x: 1.0, y: 3.1, w: 0, h: 0.3, flipV: true, line: { color: BLUE, width: 1.25, endArrowType: "triangle" } });
    txt(s, "/cmd_vel moves the UGV → new camera frame → loop repeats at 10 Hz", 3.0, 3.43, 4.5, 0.2, { fontSize: 6.5, italic: true, color: BLUE, align: "center" });
    // bottom strip: closed-loop timeline + video link
    sectionBar(pres, s, "WHAT HAPPENS WHEN THE WORLD CHANGES", 0.25, 3.82, 6.9);
    card(pres, s, 0.25, 4.12, 6.9, 1.05, "FAFBFF");
    const tl = [["bolt", AMBER, "Rock appears 7 m ahead", "detected in 1 frame → cell risk 92 → E1 → A* replan ≈ 30 ms → UGV passes with margin"],
                ["question", PURPLE, "Unfamiliar object", "no class fits → energy score high → UNKNOWN → risk 60 + 50·u → treated as lethal, wider berth"],
                ["cloudsun", AMBER, "Sun dims / shadows", "confidence 0.95 → 0.47 → CONSERVATIVE: v 1.6 → 0.5 m/s, margin ×2, only risk < 66 driven"],
                ["flag", GREEN, "Light returns", "confidence recovers → NORMAL band → speed resumes → Point B reached, zero collisions"]];
    tl.forEach(([ic, col, t, d], i) => { const x = 0.35 + i * 1.72; s.addImage({ data: ICONS[ic], x, y: 4.2, w: 0.22, h: 0.22 }); txt(s, t, x + 0.27, 4.18, 1.4, 0.2, { fontSize: 7.2, bold: true, color: col }); txt(s, d, x, 4.42, 1.62, 0.72, { fontSize: 6.3, color: TEXT }); });
    card(pres, s, 7.3, 3.82, 2.45, 1.35, LIGHT.red, "F1B9B9");
    s.addImage({ data: ICONS.video, x: 7.42, y: 3.9, w: 0.28, h: 0.28 });
    txt(s, "PROTOTYPE VIDEO", 7.75, 3.9, 1.9, 0.28, { fontSize: 10, bold: true, color: RED, valign: "middle" });
    txt(s, "Closed-loop simulation: risk map, unknown object, lighting event, replanning, A → B.", 7.42, 4.22, 2.25, 0.45, { fontSize: 7, color: TEXT });
    txt(s, "[YouTube link – add before submission]", 7.42, 4.72, 2.25, 0.35, { fontSize: 7.5, bold: true, color: INK });
    s.addNotes("Architecture: perception and localisation run in parallel and feed one risk map; the governor closes the loop from perception quality back into planning parameters.");
  }

  // ---------------------------------------------------------- slide 4
  {
    const s = pres.addSlide();
    chrome(pres, s, 4, "TECH STACK AND FEASIBILITY");
    sectionBar(pres, s, "TECHNOLOGIES USED", 0.25, 0.95, 4.55);
    const tech = [
      ["Simulation", "ROS 2 Jazzy · Gazebo Harmonic · segmentation & RGB-D camera sensors · scenario runner (YAML)", "cube", LIGHT.blue, BLUE],
      ["Perception AI", "PyTorch · SegFormer-B0 (3.7 M params) / Fast-SCNN · energy-score OOD · ONNX Runtime / TensorRT", "brain", LIGHT.purple, PURPLE],
      ["Localisation", "RTAB-Map (RGB-D) · robot_localization EKF · own ORB + PnP visual odometry as fallback", "crosshair", LIGHT.teal, TEAL],
      ["Planning & control", "NumPy multi-layer risk map · A* (scikit-image / pyastar2d) · arc-sampling local planner · pure pursuit", "route", LIGHT.green, GREEN],
      ["Dashboard & eval", "Foxglove Studio · FastAPI + WebSocket web view · seeded evaluation harness · CSV metrics", "chart", LIGHT.amber, AMBER],
      ["Proof-of-concept (now)", "Pure Python: NumPy · SciPy · scikit-image · Matplotlib renderer · imageio (demo video, slide 6)", "code", LIGHT.grey, INK],
    ];
    tech.forEach(([t, d, ic, fill, col], i) => {
      const x = 0.25 + (i % 2) * 2.3, y = 1.27 + Math.floor(i / 2) * 0.82;
      card(pres, s, x, y, 2.25, 0.74, fill, "D9DCE3");
      iconCircle(pres, s, ic, x + 0.08, y + 0.1, 0.34, col);
      txt(s, t, x + 0.5, y + 0.06, 1.7, 0.2, { fontSize: 8.5, bold: true, color: col });
      txt(s, d, x + 0.5, y + 0.26, 1.7, 0.46, { fontSize: 6.4, color: TEXT });
    });
    sectionBar(pres, s, "WHY THIS IS BUILDABLE BY A STUDENT TEAM", 0.25, 3.78, 4.55);
    card(pres, s, 0.25, 4.08, 4.55, 1.1, "F7F9FD");
    const why = ["Simulator auto-labels every training frame → no manual annotation; RUGD / RELLIS-3D / ORFD for real-image fine-tuning.",
                 "Every module is NumPy-level maths on a 0.25 m grid; A* replans in ~30 ms, whole loop runs at 10 Hz on a laptop CPU.",
                 "Same ROS 2 nodes run on a Jetson with a RealSense / ZED camera — the simulator is swapped, not the code.",
                 "Working proof-of-concept already exists (video, slide 6): 45 seeded runs, 3 planner variants."];
    txt(s, why.map((w, i) => ({ text: w, options: { bullet: { indent: 8 }, breakLine: i < why.length - 1 } })), 0.35, 4.13, 4.35, 1.0, { fontSize: 6.9, paraSpaceAfter: 2 });

    sectionBar(pres, s, "POTENTIAL CHALLENGES & RISKS", 5.0, 0.95, 4.75, RED);
    const risks = ["Textureless grass and sky make visual SLAM lose tracking outdoors.", "Segmentation degrades under strong shadows, dusk and glare.", "Objects never seen in training are misclassified as 'safe'.", "Sim-to-real gap: simulator textures differ from real terrain."];
    risks.forEach((r, i) => { card(pres, s, 5.0, 1.27 + i * 0.36, 4.75, 0.3, LIGHT.red, "F1B9B9"); s.addShape(pres.ShapeType.ellipse, { x: 5.1, y: 1.36 + i * 0.36, w: 0.1, h: 0.1, fill: { color: RED }, line: { color: RED } }); txt(s, r, 5.27, 1.27 + i * 0.36, 4.4, 0.3, { fontSize: 7.2, valign: "middle" }); });
    sectionBar(pres, s, "ANALYSIS OF FEASIBILITY", 5.0, 2.76, 4.75, AMBER);
    const feas = ["All components are proven open-source parts (RTAB-Map, ROS 2, SegFormer) — the novelty is in how they are combined.", "Risk table, bands and thresholds live in YAML — tunable without retraining.", "Prototype loop runs 10 Hz on CPU; model is ~3.7 M params → embedded-ready (ONNX / TensorRT).", "10-week plan: A→B with ground-truth pose by week 3, full stack by week 8."];
    feas.forEach((r, i) => { card(pres, s, 5.0, 3.08 + i * 0.3, 4.75, 0.26, LIGHT.amber, "F3D9A8"); s.addShape(pres.ShapeType.ellipse, { x: 5.1, y: 3.16 + i * 0.3, w: 0.1, h: 0.1, fill: { color: AMBER }, line: { color: AMBER } }); txt(s, r, 5.27, 3.08 + i * 0.3, 4.4, 0.26, { fontSize: 6.8, valign: "middle" }); });
    sectionBar(pres, s, "STRATEGIES FOR OVERCOMING RISKS", 5.0, 4.32, 4.75, PURPLE);
    const strat = ["Fuse VO with wheel odometry (EKF); tracking-health signal → hold and re-acquire.", "Confidence governor slows and widens margins when lighting degrades; CLAHE pre-processing.", "Energy-score OOD + 'novel' class trained by outlier exposure in simulation → unknown gets risk.", "Domain randomisation (sun, textures, fog) + fine-tune on RUGD / RELLIS-3D real images."];
    strat.forEach((r, i) => { txt(s, [{ text: "● ", options: { color: PURPLE } }, { text: r }], 5.05, 4.62 + i * 0.145, 4.7, 0.16, { fontSize: 6.6 }); });
    s.addNotes("Tech stack matches the earlier deck's structure: technologies, feasibility, risks, mitigations.");
  }

  // ---------------------------------------------------------- slide 5
  {
    const s = pres.addSlide();
    chrome(pres, s, 5, "IMPACT AND BENEFITS");
    sectionBar(pres, s, "IMPACT AREAS — what changes for outdoor UGV operations", 0.25, 0.95, 6.3);
    const areas = [
      ["plane", "GPS-denied defence mobility", "UGVs keep moving under jamming, in forests, valleys and urban canyons where GNSS fails — BEL's core use case.", LIGHT.blue, NAVY],
      ["ambulance", "Search & rescue", "Reaches casualties over rubble and unstable ground; unknown debris is avoided, not driven into.", LIGHT.red, RED],
      ["tractor", "Agriculture", "Field robots choose firm ground over mud, cutting bogging and crop damage; runs on a low-cost camera.", LIGHT.green, GREEN],
      ["truck", "Delivery, surveillance, mining", "Perimeter patrol and last-mile logistics at dawn, dusk and under tree cover with adaptive caution.", LIGHT.amber, AMBER],
    ];
    areas.forEach(([ic, t, d, fill, col], i) => {
      const x = 0.25 + (i % 2) * 3.2, y = 1.27 + Math.floor(i / 2) * 0.86;
      card(pres, s, x, y, 3.1, 0.78, fill, "D9DCE3");
      iconCircle(pres, s, ic, x + 0.08, y + 0.12, 0.38, col);
      txt(s, t, x + 0.55, y + 0.07, 2.5, 0.2, { fontSize: 8.5, bold: true, color: col });
      txt(s, d, x + 0.55, y + 0.27, 2.5, 0.5, { fontSize: 6.6, color: TEXT });
    });
    sectionBar(pres, s, "KEY PROGRAM IMPACTS", 0.25, 3.05, 6.3);
    const kp = [["Collision-free autonomy", "0 collisions in 45 seeded runs; unknown objects and ditches avoided, not assumed safe.", GREEN],
                ["Safer, not just shorter", "Time in mud cut from ~40 s to under 1 s per run vs. binary planner; path ~13 % longer.", NAVY],
                ["Self-aware perception", "Confidence score tells the vehicle when to slow down — a first-class signal.", PURPLE],
                ["Fast reaction", "New hazard detected within 1–2 frames, ~100–200 ms (binary map: ~960 ms); A* replan in under 30 ms.", AMBER],
                ["Low cost, lightweight", "One RGB-D camera, no LiDAR, no GPS; 3.7 M-param model runs on Jetson-class boards.", TEAL],
                ["Measurable & reproducible", "Seeded scenarios and ablations; every claim is a number from the harness.", RED]];
    kp.forEach(([t, d, col], i) => {
      const x = 0.25 + (i % 3) * 2.13, y = 3.37 + Math.floor(i / 3) * 0.66;
      card(pres, s, x, y, 2.05, 0.6, "FFFFFF", "D9DCE3");
      txt(s, t, x + 0.08, y + 0.05, 1.9, 0.18, { fontSize: 7.8, bold: true, color: col });
      txt(s, d, x + 0.08, y + 0.23, 1.9, 0.36, { fontSize: 6.3, color: TEXT });
    });
    // right column
    sectionBar(pres, s, "TARGET AUDIENCE", 6.75, 0.95, 3.0);
    const ta = [["1", "BEL / defence UGV programmes", "Camera-first autonomy module for GPS-denied outdoor platforms.", NAVY, LIGHT.blue],
                ["2", "Disaster-response agencies (NDRF, SDRF)", "Ground robots for reconnaissance over unstable terrain.", RED, LIGHT.red],
                ["3", "Agri-robotics & plantation operators", "Low-cost navigation for field and orchard vehicles.", GREEN, LIGHT.green],
                ["4", "Logistics, mining & surveillance", "Perimeter and last-mile autonomy in unstructured sites.", AMBER, LIGHT.amber],
                ["5", "Robotics researchers & students", "Open, simulator-agnostic reference stack with evaluation harness.", PURPLE, LIGHT.purple]];
    ta.forEach(([n, t, d, col, fill], i) => {
      const y = 1.27 + i * 0.5;
      card(pres, s, 6.75, y, 3.0, 0.44, fill, "D9DCE3");
      s.addShape(pres.ShapeType.ellipse, { x: 6.83, y: y + 0.1, w: 0.24, h: 0.24, fill: { color: col }, line: { color: col } });
      txt(s, n, 6.83, y + 0.1, 0.24, 0.24, { fontSize: 8, bold: true, color: "FFFFFF", align: "center", valign: "middle" });
      txt(s, t, 7.15, y + 0.03, 2.55, 0.18, { fontSize: 7.4, bold: true, color: col });
      txt(s, d, 7.15, y + 0.21, 2.55, 0.22, { fontSize: 6.3, color: TEXT });
    });
    sectionBar(pres, s, "WHO GAINS WHAT", 6.75, 3.82, 3.0);
    const wg = [["Operator", "Vehicle reaches the objective without babysitting; risk appetite is one slider."], ["Platform maker", "Drop-in software module; camera only, no GPS/LiDAR bill of materials."], ["Mission", "Fewer stuck or damaged vehicles; predictable, explainable behaviour."]];
    wg.forEach(([a, b], i) => { const y = 4.14 + i * 0.35; card(pres, s, 6.75, y, 3.0, 0.31, i % 2 ? "FFFFFF" : LIGHT.grey, "E0E3EA"); txt(s, a, 6.83, y, 0.8, 0.31, { fontSize: 7, bold: true, color: NAVY, valign: "middle" }); txt(s, b, 7.6, y, 2.1, 0.31, { fontSize: 6.2, valign: "middle" }); });
    card(pres, s, 0.25, 4.75, 6.3, 0.42, INK, INK);
    txt(s, "Right terrain · right speed · right margin — collision-free Point A → Point B without GPS", 0.35, 4.75, 6.1, 0.42, { fontSize: 9.5, bold: true, color: "FFFFFF", align: "center", valign: "middle" });
    s.addNotes("Impact slide structured like the earlier deck: impact areas, program impacts, target audience, who gains what.");
  }

  // ---------------------------------------------------------- slide 6
  {
    const s = pres.addSlide();
    chrome(pres, s, 6, "RESEARCH AND REFERENCES");
    txt(s, "PROJECT LINKS & DEMO", 0.3, 0.9, 4.0, 0.25, { fontSize: 11, bold: true, color: NAVY });
    const shot = ["03_unknown_full.png", "05_recovered_full.png", "04_lowlight_full.png", "06_goal_full.png"].map(f => path.join(PROTO, f)).find(f => fs.existsSync(f));
    if (shot) s.addImage({ path: shot, x: 0.3, y: 1.17, w: 4.55, h: 2.56 });
    else card(pres, s, 0.3, 1.17, 4.55, 2.56, LIGHT.grey);
    txt(s, "Proof-of-concept dashboard (t = 32 s): an unfamiliar object is flagged UNKNOWN (magenta) in the camera and the map; the risk-aware route (white) leaves the mud belt (orange) that the shortest route (grey) crosses; VO estimate vs ground truth, confidence gauge, governor band and event log.", 0.3, 3.75, 4.55, 0.32, { fontSize: 6.1, color: MUTED });
    // results strip
    const m = M && M.full && M.full.n ? M : null;
    sectionBar(pres, s, m ? `PROTOTYPE RESULTS — ${m.full.n} seeded runs per planner, same world` : "PROTOTYPE RESULTS", 0.3, 4.06, 4.55, GREEN);
    const hdr = ["Metric", "Binary planner", "Risk-aware", "DRISHTI-Nav"];
    const rows = m ? [
      ["Success (no collision)", `${m.baseline.success} %`, `${m.risk_only.success} %`, `${m.full.success} %`],
      ["Runs with collision", `${m.baseline.collided}/${m.baseline.n}`, `${m.risk_only.collided}/${m.risk_only.n}`, `${m.full.collided}/${m.full.n}`],
      ["Time driving in mud (s, mean)", `${m.baseline.mud} s`, `${m.risk_only.mud} s`, `${m.full.mud} s`],
      ["Hazard detection latency (ms)", `${m.baseline.detect}`, `${m.risk_only.detect}`, `${m.full.detect}`],
      ["Global replans / run", `${m.baseline.replans}`, `${m.risk_only.replans}`, `${m.full.replans}`],
      ["Path length (m)", `${m.baseline.path}`, `${m.risk_only.path}`, `${m.full.path}`],
    ] : [["(run code/run_eval.py to fill)", "", "", ""]];
    const tbl = [hdr.map(h => ({ text: h, options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, fontSize: 6.5, fontFace: FONT } }))].concat(
      rows.map((r, i) => r.map((c, j) => ({ text: c, options: { fontSize: 6.5, fontFace: FONT, bold: j === 3, color: j === 3 ? GREEN : TEXT, fill: { color: i % 2 ? "FFFFFF" : "F3F4F6" } } }))));
    s.addTable(tbl, { x: 0.3, y: 4.34, w: 4.55, colW: [1.55, 1.0, 1.0, 1.0], rowH: 0.115, border: { type: "solid", color: "D9DCE3", pt: 0.5 }, margin: 0.02 });
    // links
    card(pres, s, 5.05, 0.9, 4.7, 0.62, LIGHT.red, "F1B9B9");
    s.addImage({ data: ICONS.video, x: 5.15, y: 1.02, w: 0.3, h: 0.3 });
    txt(s, "PROTOTYPE VIDEO", 5.55, 0.94, 2.5, 0.22, { fontSize: 10, bold: true, color: RED });
    txt(s, "Full walkthrough of the working simulation (4 min)  ·  [YouTube link – add before submission]", 5.55, 1.16, 4.1, 0.32, { fontSize: 7, color: TEXT });
    card(pres, s, 5.05, 1.6, 4.7, 0.62, LIGHT.blue, "B7C7E8");
    s.addImage({ data: ICONS.github, x: 5.15, y: 1.72, w: 0.3, h: 0.3 });
    txt(s, "GIT-HUB LINK", 5.55, 1.64, 2.5, 0.22, { fontSize: 10, bold: true, color: BLUE });
    txt(s, "Complete repository — simulator, perception, risk map, planner, dashboard, evaluation harness  ·  [GitHub link – add before submission]", 5.55, 1.86, 4.1, 0.32, { fontSize: 7, color: TEXT });
    txt(s, "RESEARCH & REFERENCES", 5.05, 2.32, 4.7, 0.25, { fontSize: 11, bold: true, color: NAVY });
    const refs = [
      "Wigness et al., RUGD: A Dataset for Autonomous Navigation in Unstructured Outdoor Environments, IROS 2019.",
      "Jiang et al., RELLIS-3D Dataset: Data, Benchmarks and Analysis, arXiv:2011.12954 (2020).",
      "Viswanath et al., OFFSEG: A Semantic Segmentation Framework for Off-Road Driving, 2021.",
      "Guan et al., GANav: Efficient Terrain Segmentation for Robot Navigation, IEEE RA-L 2022.",
      "Min et al., ORFD: A Dataset and Benchmark for Off-Road Freespace Detection (lighting/weather variation).",
      "Liu et al., Energy-based Out-of-distribution Detection, NeurIPS 2020.",
      "Hendrycks et al., Deep Anomaly Detection with Outlier Exposure, ICLR 2019.",
      "Lakshminarayanan et al., Simple and Scalable Predictive Uncertainty via Deep Ensembles, NeurIPS 2017.",
      "Frey et al., Fast Traversability Estimation for Wild Visual Navigation, RSS 2023; RoadRunner, ICRA 2024.",
      "Campos et al., ORB-SLAM3, IEEE T-RO 2021;  Labbé & Michaud, RTAB-Map, J. Field Robotics 2019.",
      "Macenski et al., Nav2 — ROS 2 Navigation Stack; arXiv:2407.18535 (RGB-D → costmap layer).",
      "Koenig & Likhachev, D* Lite, AAAI 2002;  Fox et al., Dynamic Window Approach, 1997.",
      "Xie et al., SegFormer, NeurIPS 2021;  Poudel et al., Fast-SCNN, BMVC 2019.",
      "BEL Problem Statement 26126, Smart India Hackathon 2026.",
    ];
    txt(s, refs.map((r, i) => ({ text: `${i + 1}. ${r}`, options: { breakLine: i < refs.length - 1 } })), 5.05, 2.58, 4.7, 2.62, { fontSize: 6.4, color: INK, paraSpaceAfter: 1.2 });
    s.addNotes("References mirror the literature review; video and GitHub links to be inserted by the team.");
  }

  await pres.writeFile({ fileName: OUT });
  console.log("wrote", OUT, M ? "with metrics" : "WITHOUT metrics (results.csv missing)");
})().catch(e => { console.error(e); process.exit(1); });
