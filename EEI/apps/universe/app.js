// 商域宇宙：EEI 的沉浸式宇宙视图。
// 每家核心公司是一颗恒星；它在官方申报里的子公司、董事、股东是行星；
// 同一个实体出现在两家公司的关系里时，拉出一道穿越星海的光弧（宇宙关联）。
// 数据全部实时读 EEI 公开接口（SEC、GLEIF 原文），页面不写死任何业务数字。
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const API = (new URLSearchParams(location.search).get("api") || "https://eei.linzezhang.com").replace(/\/$/, "");
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const MOBILE = matchMedia("(max-width: 900px)").matches;

// 恒星顺序即星系旋臂顺序：同一产业链的放在相邻位置。
const ANCHORS = [
  { id: "00000000-0000-4000-8000-000000000006", zh: "英伟达" },
  { id: "2c478a6b-81c9-5e2b-9df9-4e1b87e9a296", zh: "台积电" },
  { id: "ee6fda1a-6cce-5657-9a96-300c5833e4b1", zh: "阿斯麦" },
  { id: "00000000-0000-4000-8000-000000000005", zh: "苹果" },
  { id: "00000000-0000-4000-8000-000000000003", zh: "微软" },
  { id: "00000000-0000-4000-8000-000000000001", zh: "Alphabet" },
  { id: "00000000-0000-4000-8000-000000000002", zh: "Meta" },
  { id: "00000000-0000-4000-8000-000000000004", zh: "亚马逊" },
  { id: "00000000-0000-4000-8000-000000000008", zh: "甲骨文" },
  { id: "00000000-0000-4000-8000-000000000007", zh: "特斯拉" },
  // 伯克希尔：两跳、或一跳超过 60 个节点，上游接口都返回 500（2026-09-30 实测），直接从一跳 60 节点起
  { id: "2f0812b5-5c32-5603-9795-db788f6f7842", zh: "伯克希尔", hops: 1, maxNodes: 60 },
];
const LAYERS = ["corporate_structure", "ownership_control", "governance", "supply_chain", "capital", "business"];

const FAMILY = {
  corporate_structure: { zh: "集团结构", color: "#3fd6e0", ring: 1 },
  governance_people: { zh: "董事与高管", color: "#a878ff", ring: 0 },
  board_governance: { zh: "董事与高管", color: "#a878ff", ring: 0 },
  ownership_control: { zh: "控制与持股", color: "#ff6fc1", ring: 2 },
  supply_chain_operations: { zh: "供应链", color: "#35f0b0", ring: 3 },
  capital_financing: { zh: "资本与融资", color: "#6fa8ff", ring: 3 },
  mergers_acquisitions: { zh: "并购", color: "#ff9d5c", ring: 3 },
  other: { zh: "其他关系", color: "#9fb3c8", ring: 3 },
};
const famOf = (f) => (FAMILY[f] ? f : "other");
const LEGEND_KEYS = ["governance_people", "corporate_structure", "ownership_control", "supply_chain_operations", "capital_financing", "mergers_acquisitions", "other"];

const REL_ZH = {
  subsidiary_of: "子公司", parent_of: "母公司", voting_control: "表决权控制", beneficial_owner: "实益所有人",
  controls: "控制", controlled_by: "受控于", owns_stake_in: "持股", board_member_of: "董事", director_of: "董事",
  officer_of: "高管", executive_of: "高管", supplier_to: "供应商", customer_of: "客户", wafer_foundry_for: "晶圆代工",
  packages_tests_for: "封装测试", equipment_provider_to: "设备供应商", material_provider_to: "材料供应商",
  invests_in: "投资", acquired: "收购", acquired_by: "被收购", merged_with: "合并", divested: "出售",
};
const relZh = (t) => REL_ZH[t] || (t || "关系").replace(/_/g, " ");

// ---------- 名称：全大写法定名转成人能读的写法 ----------
const KEEP_UPPER = new Set(["LLC", "LP", "LLP", "PLC", "AG", "SA", "NV", "BV", "AB", "AS", "SE", "KK", "USA", "US", "UK", "EU", "II", "III", "IV", "AI", "TSMC", "ASML", "IBM", "HK", "SAS", "SRL", "SPA", "GK", "PTE", "LTDA", "CV", "SARL", "OY", "ULC", "SLU"]);
function prettyName(raw) {
  if (!raw) return "未命名实体";
  const s = String(raw).trim();
  const letters = s.replace(/[^A-Za-z]/g, "");
  if (!letters || letters !== letters.toUpperCase() || letters.length < 3) return s;
  return s.toLowerCase().replace(/[a-z][a-z'.&]*/g, (w) => {
    const bare = w.replace(/[.']/g, "").toUpperCase();
    if (KEEP_UPPER.has(bare)) return w.toUpperCase();
    if (["of", "and", "de", "du", "la", "le", "the", "für", "und"].includes(w)) return w;
    return w[0].toUpperCase() + w.slice(1);
  }).replace(/^./, (c) => c.toUpperCase());
}
const SUFFIX = /[,\s]+(inc\.?|incorporated|corporation|corp\.?|company|co\.?|limited|ltd\.?|llc|l\.l\.c\.|plc|n\.v\.|b\.v\.|ag|s\.a\.|gmbh|holdings?|private limited|pte\.? ltd\.?)$/i;
function shortName(raw) {
  let s = prettyName(raw).replace(/\s*\([^)]*\)\s*$/, "");
  for (let i = 0; i < 3; i++) s = s.replace(SUFFIX, "");
  return s.length > 34 ? s.slice(0, 32) + "…" : s;
}
const fmt = (n) => (typeof n === "number" ? n.toLocaleString("zh-CN") : "—");

// ---------- 渲染器与场景 ----------
const canvas = document.getElementById("cosmos");
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
} catch (err) {
  const box = document.getElementById("state");
  box.querySelector(".state-core").style.animation = "none";
  document.getElementById("state-text").innerHTML = '这个浏览器没有开启 3D 图形（WebGL），宇宙视图画不出来。<br>换用最新版 Chrome、Safari 或 Edge，或在浏览器设置里打开「硬件加速」后刷新。<br><a href="https://eei.linzezhang.com/" style="color:#3fd6e0">先去看平面版完整图谱 ↗</a>';
  throw err;
}
renderer.setPixelRatio(Math.min(window.devicePixelRatio, MOBILE ? 1.5 : 2));
renderer.setSize(innerWidth, innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
scene.background = new THREE.Color("#020708");
scene.fog = new THREE.FogExp2("#031113", 0.00042);

const camera = new THREE.PerspectiveCamera(52, innerWidth / innerHeight, 0.5, 9000);
camera.position.set(0, 1500, 1900);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.rotateSpeed = 0.55;
controls.zoomSpeed = 0.9;
controls.minDistance = 40;
controls.maxDistance = 2600;
controls.maxPolarAngle = Math.PI * 0.86;
controls.autoRotate = !REDUCED;
controls.autoRotateSpeed = 0.22;

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.78, 0.5, 0.2);
composer.addPass(bloom);
composer.addPass(new OutputPass());

const clock = new THREE.Clock();
const uTime = { value: 0 };

// ---------- 程序化贴图 ----------
function radialTexture(stops, size = 256) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  const grd = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  for (const [o, col] of stops) grd.addColorStop(o, col);
  g.fillStyle = grd;
  g.fillRect(0, 0, size, size);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
const TEX_GLOW = radialTexture([[0, "rgba(255,255,255,1)"], [0.18, "rgba(255,255,255,.55)"], [0.45, "rgba(255,255,255,.12)"], [1, "rgba(255,255,255,0)"]]);
const TEX_SOFT = radialTexture([[0, "rgba(255,255,255,.9)"], [0.5, "rgba(255,255,255,.25)"], [1, "rgba(255,255,255,0)"]], 128);
const TEX_NEBULA = radialTexture([[0, "rgba(255,255,255,.55)"], [0.35, "rgba(255,255,255,.2)"], [0.7, "rgba(255,255,255,.05)"], [1, "rgba(255,255,255,0)"]], 512);
function raysTexture(n = 16, size = 512) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  g.translate(size / 2, size / 2);
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    const len = size * (i % 2 ? 0.34 : 0.48);
    const w = i % 2 ? 0.035 : 0.055;
    const grd = g.createLinearGradient(0, 0, Math.cos(a) * len, Math.sin(a) * len);
    grd.addColorStop(0, "rgba(255,226,160,.9)");
    grd.addColorStop(1, "rgba(255,190,90,0)");
    g.fillStyle = grd;
    g.beginPath();
    g.moveTo(0, 0);
    g.lineTo(Math.cos(a - w) * len, Math.sin(a - w) * len);
    g.lineTo(Math.cos(a + w) * len, Math.sin(a + w) * len);
    g.closePath();
    g.fill();
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
const TEX_RAYS = raysTexture();

// ---------- 背景：星空、星云、漂浮尘埃 ----------
function makeStars(count, rMin, rMax, size) {
  const g = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3), seed = new Float32Array(count), col = new Float32Array(count * 3);
  const palette = [new THREE.Color("#ffffff"), new THREE.Color("#bfe9ff"), new THREE.Color("#ffe6b8"), new THREE.Color("#9ff5ea")];
  for (let i = 0; i < count; i++) {
    const r = rMin + Math.random() * (rMax - rMin), th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1);
    pos.set([r * Math.sin(ph) * Math.cos(th), r * Math.cos(ph) * 0.6, r * Math.sin(ph) * Math.sin(th)], i * 3);
    seed[i] = Math.random();
    const c = palette[(Math.random() * palette.length) | 0];
    col.set([c.r, c.g, c.b], i * 3);
  }
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("seed", new THREE.BufferAttribute(seed, 1));
  g.setAttribute("color", new THREE.BufferAttribute(col, 3));
  const m = new THREE.ShaderMaterial({
    uniforms: { uTime, uSize: { value: size * renderer.getPixelRatio() }, uMap: { value: TEX_SOFT } },
    vertexShader: `attribute float seed; varying float vS; varying vec3 vC; uniform float uTime; uniform float uSize;
      void main(){ vS=seed; vC=color; vec4 mv=modelViewMatrix*vec4(position,1.0); gl_Position=projectionMatrix*mv;
      float tw=0.55+0.45*sin(uTime*(0.6+seed*1.8)+seed*40.0); gl_PointSize=uSize*(0.35+seed*0.9)*tw*(900.0/-mv.z); }`,
    fragmentShader: `uniform sampler2D uMap; varying float vS; varying vec3 vC;
      void main(){ vec4 t=texture2D(uMap,gl_PointCoord); gl_FragColor=vec4(vC, t.a*(0.35+0.65*vS)); }`,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, vertexColors: true,
  });
  return new THREE.Points(g, m);
}
scene.add(makeStars(MOBILE ? 2600 : 6500, 1800, 4200, 7));
const dust = makeStars(MOBILE ? 500 : 1400, 80, 1100, 3.2);
dust.material.uniforms.uSize.value = 3.2 * renderer.getPixelRatio();
scene.add(dust);

const nebulae = new THREE.Group();
[["#0a4b4b", 1500, 0.55], ["#0d6b6b", 1100, 0.35], ["#3b1f6b", 1300, 0.28], ["#0a3550", 1700, 0.4], ["#5a2f10", 900, 0.18], ["#0a4b4b", 900, 0.3]].forEach(([c, s, o], i) => {
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: TEX_NEBULA, color: c, transparent: true, opacity: o, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
  const a = i * 1.7;
  sp.position.set(Math.cos(a) * 520, -160 + (i % 3) * 90, Math.sin(a) * 520);
  sp.scale.setScalar(s);
  nebulae.add(sp);
});
scene.add(nebulae);

// ---------- 数据 ----------
async function getJSON(path, init) {
  const r = await fetch(API + path, init);
  if (!r.ok) throw new Error(`${path} → HTTP ${r.status}`);
  return r.json();
}
async function exploreGraph(id, startHops = 2, startNodes = 160) {
  const tries = [{ hops: 2, max_nodes: 160, max_edges: 320 }, { hops: 1, max_nodes: 90, max_edges: 120 }, { hops: 1, max_nodes: 60, max_edges: 80 }, { hops: 1, max_nodes: 40, max_edges: 60 }].filter((t) => t.hops <= startHops && t.max_nodes <= startNodes);
  let last;
  for (const t of tries) {
    const body = { focus: { object_type: "entity", object_id: id }, active_layers: LAYERS, direction: "both", hops: t.hops, filters: {}, budget: { max_nodes: t.max_nodes, max_edges: t.max_edges, expand_nodes: 40 } };
    try { return await getJSON("/v1/explore", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }); }
    catch (e) { last = e; }
  }
  throw last;
}

const nodes = new Map(); // id → node
const edges = new Map(); // id → edge
const systems = [];      // 每颗恒星一个星系
const hiddenFamilies = new Set();

function upsertNode(n) {
  let node = nodes.get(n.id);
  if (!node) {
    node = { id: n.id, raw: n.canonical_name, name: prettyName(n.canonical_name), short: shortName(n.canonical_name), type: n.entity_type, system: null, isSun: false, edges: new Set(), pos: new THREE.Vector3(), fam: "other" };
    nodes.set(n.id, node);
  }
  return node;
}

// ---------- 布局：恒星在旋臂上，行星在倾斜的轨道盘上 ----------
function sunPosition(i) {
  const a = i * 2.2 + 0.4;
  const r = 170 + i * 58;
  return new THREE.Vector3(Math.cos(a) * r, Math.sin(i * 1.3) * 40, Math.sin(a) * r);
}
const RING_R = [26, 40, 54, 68];
function layoutSystem(sys) {
  const sun = sys.sun;
  const tilt = new THREE.Euler((Math.sin(sys.index * 2.1) * 0.45), 0, (Math.cos(sys.index * 1.7) * 0.4));
  sys.tilt = new THREE.Quaternion().setFromEuler(tilt);
  const rings = [[], [], [], []];
  for (const p of sys.planets) rings[FAMILY[p.fam].ring].push(p);
  rings.forEach((list, ri) => {
    const r = RING_R[ri] + Math.min(list.length, 30) * 0.35;
    sys.ringRadii[ri] = list.length ? r : 0;
    list.forEach((p, k) => {
      const a = k * 2.399963 + ri * 0.7;
      const rr = r + ((k * 7) % 5 - 2) * 1.2;
      const local = new THREE.Vector3(Math.cos(a) * rr, ((k * 13) % 7 - 3) * 0.9, Math.sin(a) * rr).applyQuaternion(sys.tilt);
      p.pos.copy(sun.pos).add(local);
      p.orbit = { r: rr, a, y: local.y, speed: (0.018 + 0.012 / (ri + 1)) * (k % 2 ? 1 : 0.85) };
    });
  });
  for (const m of sys.moons) {
    const host = m.host;
    const a = (m.id.charCodeAt(0) + m.id.charCodeAt(5)) % 628 / 100;
    m.moon = { a, r: 5 + (m.id.charCodeAt(3) % 4) };
    m.pos.copy(host.pos).add(new THREE.Vector3(Math.cos(a) * m.moon.r, 1.5, Math.sin(a) * m.moon.r));
  }
}

// ---------- 天体对象 ----------
const pickables = [];
const labelsLayer = document.body;
function makeLabel(node) {
  const el = document.createElement("div");
  el.className = "label" + (node.isSun ? " sun" : "");
  if (node.isSun) el.innerHTML = node.zh.toLowerCase() === node.short.toLowerCase() || node.short.toLowerCase().startsWith(node.zh.toLowerCase()) ? escapeHTML(node.short) : `${node.zh}<small>${escapeHTML(node.short)}</small>`;
  else el.textContent = node.short;
  el.style.opacity = "0";
  labelsLayer.appendChild(el);
  node.label = el;
}
function escapeHTML(s) { return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

function buildSun(sys) {
  const n = sys.sun;
  const cross = [...n.edges].filter((id) => { const e = edges.get(id); const a = nodes.get(e?.subject_id), b = nodes.get(e?.object_id); return a && b && a.system !== b.system; }).length;
  const size = Math.max(10, 7 + Math.sqrt(sys.planets.length + sys.moons.length + cross * 6) * 1.7);
  const g = new THREE.Group();
  g.position.copy(n.pos);
  const core = new THREE.Mesh(new THREE.SphereGeometry(size * 0.42, 40, 40), new THREE.MeshBasicMaterial({ color: new THREE.Color("#ffc65c").multiplyScalar(1.5) }));
  const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: TEX_GLOW, color: "#e0a843", transparent: true, opacity: 0.8, depthWrite: false, blending: THREE.AdditiveBlending }));
  glow.scale.setScalar(size * 2.6);
  const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: TEX_GLOW, color: "#ff9a3c", transparent: true, opacity: 0.12, depthWrite: false, blending: THREE.AdditiveBlending }));
  halo.scale.setScalar(size * 4.6);
  const rays = new THREE.Sprite(new THREE.SpriteMaterial({ map: TEX_RAYS, color: "#ffdca0", transparent: true, opacity: 0.42, depthWrite: false, blending: THREE.AdditiveBlending }));
  rays.scale.setScalar(size * 5.2);
  g.add(halo, glow, rays, core);
  // 轨道环：星系的「星图仪」感
  const ringMat = new THREE.LineBasicMaterial({ color: "#3fd6e0", transparent: true, opacity: 0.09, depthWrite: false, blending: THREE.AdditiveBlending });
  sys.ringRadii.forEach((r) => {
    if (!r) return;
    const pts = [];
    for (let i = 0; i <= 128; i++) { const a = (i / 128) * Math.PI * 2; pts.push(new THREE.Vector3(Math.cos(a) * r, 0, Math.sin(a) * r).applyQuaternion(sys.tilt)); }
    g.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), ringMat));
  });
  const pick = new THREE.Mesh(new THREE.SphereGeometry(size * 1.3, 12, 12), new THREE.MeshBasicMaterial({ visible: false }));
  pick.userData.node = n;
  g.add(pick);
  pickables.push(pick);
  scene.add(g);
  n.obj = { group: g, core, glow, halo, rays, size, baseOpacity: 1 };
  makeLabel(n);
}

const planetGeo = new THREE.SphereGeometry(1, 20, 20);
function buildPlanet(p) {
  const color = new THREE.Color(FAMILY[p.fam].color);
  const person = p.type === "person";
  const size = (person ? 2.3 : 3.1) + Math.min(p.edges.size, 8) * 0.25;
  const g = new THREE.Group();
  g.position.copy(p.pos);
  const core = new THREE.Mesh(planetGeo, new THREE.MeshBasicMaterial({ color: color.clone().multiplyScalar(1.9), transparent: true }));
  core.scale.setScalar(size * 0.55);
  const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: TEX_GLOW, color, transparent: true, opacity: 0.9, depthWrite: false, blending: THREE.AdditiveBlending }));
  glow.scale.setScalar(size * 3.4);
  g.add(glow, core);
  const pick = new THREE.Mesh(new THREE.SphereGeometry(size * 1.6, 8, 8), new THREE.MeshBasicMaterial({ visible: false }));
  pick.userData.node = p;
  g.add(pick);
  pickables.push(pick);
  scene.add(g);
  p.obj = { group: g, core, glow, size, color };
  makeLabel(p);
}

// ---------- 光弧：弯曲、发光、光沿路径行进 ----------
const arcMaterialCache = new Map();
function arcMaterial(color, cross) {
  const key = color + (cross ? "x" : "");
  if (arcMaterialCache.has(key)) return arcMaterialCache.get(key);
  const m = new THREE.ShaderMaterial({
    uniforms: { uTime, uColor: { value: new THREE.Color(color) }, uCross: { value: cross ? 1 : 0 }, uDim: { value: 1 } },
    vertexShader: `attribute float t; attribute float seed; varying float vT; varying float vSeed; void main(){ vT=t; vSeed=seed; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
    fragmentShader: `uniform float uTime; uniform vec3 uColor; uniform float uCross; uniform float uDim; varying float vT; varying float vSeed;
      void main(){
        float speed = mix(0.22, 0.12, uCross);
        float head = fract(uTime*speed + vSeed);
        float d = vT - head; d = d - floor(d + 0.5);
        float pulse = exp(-pow(d*mix(14.0, 9.0, uCross), 2.0));
        float base = mix(0.16, 0.22, uCross) * (0.6 + 0.4*sin(vT*3.14159));
        vec3 col = mix(uColor, vec3(1.0,0.9,0.7), pulse*0.5);
        gl_FragColor = vec4(col*(1.0+pulse*1.8), (base + pulse*0.9) * uDim);
      }`,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
  arcMaterialCache.set(key, m);
  return m;
}
function curvePoints(a, b, lift, segs) {
  const mid = a.clone().add(b).multiplyScalar(0.5);
  const dist = a.distanceTo(b);
  const ctrl = mid.add(new THREE.Vector3(0, lift * dist, 0));
  const c = new THREE.QuadraticBezierCurve3(a.clone(), ctrl, b.clone());
  return c.getPoints(segs);
}
const arcs = [];
function buildArc(edge) {
  const a = nodes.get(edge.subject_id), b = nodes.get(edge.object_id);
  if (!a || !b) return;
  const cross = a.system !== b.system;
  const fam = famOf(edge.relationship_family);
  const color = cross ? "#ffc861" : FAMILY[fam].color;
  const segs = cross ? 96 : 32;
  const pts = curvePoints(a.pos, b.pos, cross ? 0.32 : 0.18, segs);
  const g = new THREE.BufferGeometry().setFromPoints(pts);
  const t = new Float32Array(pts.length), seed = new Float32Array(pts.length);
  const s = (edge.id.charCodeAt(1) * 7 + edge.id.charCodeAt(4)) % 100 / 100;
  for (let i = 0; i < pts.length; i++) { t[i] = i / (pts.length - 1); seed[i] = s; }
  g.setAttribute("t", new THREE.BufferAttribute(t, 1));
  g.setAttribute("seed", new THREE.BufferAttribute(seed, 1));
  const mat = arcMaterial(color, cross).clone();
  mat.uniforms.uTime = uTime;
  const line = new THREE.Line(g, mat);
  line.frustumCulled = false;
  scene.add(line);
  const arc = { edge, line, a, b, cross, fam, pts };
  arcs.push(arc);
  edge.arc = arc;
}
// 沿光弧飞行的粒子
let flyers = null;
function buildFlyers() {
  const list = arcs.filter((a) => a.cross || !MOBILE);
  const count = Math.min(list.length * 2, MOBILE ? 160 : 520);
  const g = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3), col = new Float32Array(count * 3), seed = new Float32Array(count);
  const meta = [];
  for (let i = 0; i < count; i++) {
    const arc = list[i % list.length];
    const c = new THREE.Color(arc.cross ? "#ffe0a0" : FAMILY[arc.fam].color);
    col.set([c.r, c.g, c.b], i * 3);
    seed[i] = Math.random();
    meta.push({ arc, off: Math.random(), speed: arc.cross ? 0.05 + Math.random() * 0.04 : 0.12 + Math.random() * 0.1 });
  }
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.BufferAttribute(col, 3));
  g.setAttribute("seed", new THREE.BufferAttribute(seed, 1));
  const m = new THREE.ShaderMaterial({
    uniforms: { uTime, uSize: { value: 9 * renderer.getPixelRatio() }, uMap: { value: TEX_SOFT } },
    vertexShader: `attribute float seed; varying vec3 vC; uniform float uSize; void main(){ vC=color; vec4 mv=modelViewMatrix*vec4(position,1.0); gl_Position=projectionMatrix*mv; gl_PointSize=uSize*(0.6+seed*0.6)*(300.0/-mv.z); }`,
    fragmentShader: `uniform sampler2D uMap; varying vec3 vC; void main(){ vec4 t=texture2D(uMap,gl_PointCoord); gl_FragColor=vec4(vC*1.6, t.a); }`,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, vertexColors: true,
  });
  const pts = new THREE.Points(g, m);
  pts.frustumCulled = false;
  scene.add(pts);
  flyers = { pts, meta };
}
function updateFlyers(t) {
  if (!flyers) return;
  const arr = flyers.pts.geometry.attributes.position.array;
  flyers.meta.forEach((f, i) => {
    const hidden = f.arc.line.visible === false;
    const pts = f.arc.pts;
    const u = hidden ? 0 : (f.off + t * f.speed) % 1;
    const x = u * (pts.length - 1), k = Math.floor(x), fr = x - k;
    const p0 = pts[k], p1 = pts[Math.min(k + 1, pts.length - 1)];
    arr[i * 3] = hidden ? 99999 : p0.x + (p1.x - p0.x) * fr;
    arr[i * 3 + 1] = p0.y + (p1.y - p0.y) * fr;
    arr[i * 3 + 2] = p0.z + (p1.z - p0.z) * fr;
  });
  flyers.pts.geometry.attributes.position.needsUpdate = true;
}

// ---------- 装配宇宙 ----------
async function loadUniverse() {
  const results = await Promise.allSettled(ANCHORS.map((a) => exploreGraph(a.id, a.hops || 2, a.maxNodes || 160)));
  const ok = [];
  results.forEach((r, i) => { if (r.status === "fulfilled" && r.value?.focus) ok.push({ anchor: ANCHORS[i], g: r.value }); });
  if (!ok.length) throw new Error("所有恒星的数据都没取到");
  ok.forEach(({ anchor, g }) => {
    const sun = upsertNode({ id: g.focus.id, canonical_name: g.focus.canonical_name, entity_type: g.focus.entity_type });
    sun.isSun = true;
    sun.zh = anchor.zh;
  });
  ok.forEach(({ g }, idx) => {
    const sun = nodes.get(g.focus.id);
    const sys = { index: idx, sun, planets: [], moons: [], ringRadii: [0, 0, 0, 0], nodeCount: g.nodes.length, edgeCount: g.edges.length };
    sun.system = sys;
    sun.pos.copy(sunPosition(idx));
    systems.push(sys);
    for (const n of g.nodes) upsertNode(n);
    for (const e of g.edges) {
      if (!edges.has(e.id)) edges.set(e.id, { ...e });
      nodes.get(e.subject_id)?.edges.add(e.id);
      nodes.get(e.object_id)?.edges.add(e.id);
    }
    // 直接挂在恒星上的是行星，挂在行星上的是卫星
    const direct = new Map();
    for (const e of g.edges) {
      const other = e.subject_id === sun.id ? e.object_id : e.object_id === sun.id ? e.subject_id : null;
      if (other && !direct.has(other)) direct.set(other, famOf(e.relationship_family));
    }
    for (const [id, fam] of direct) {
      const n = nodes.get(id);
      if (!n || n.isSun || n.system) continue;
      n.system = sys; n.fam = fam; n.role = "planet";
      sys.planets.push(n);
    }
    for (const e of g.edges) {
      for (const [x, y] of [[e.subject_id, e.object_id], [e.object_id, e.subject_id]]) {
        const n = nodes.get(x), host = nodes.get(y);
        if (!n || n.isSun || n.system || !host || host.role !== "planet" || host.system !== sys) continue;
        n.system = sys; n.fam = famOf(e.relationship_family); n.role = "moon"; n.host = host;
        sys.moons.push(n);
      }
    }
  });
  // 还没有归属的（只和别的星系相连）放到最近一个相连的星系外圈
  for (const n of nodes.values()) {
    if (n.system) continue;
    const e = edges.get([...n.edges][0]);
    const other = e && nodes.get(e.subject_id === n.id ? e.object_id : e.subject_id);
    const sys = other?.system || systems[0];
    n.system = sys; n.fam = famOf(e?.relationship_family); n.role = "planet";
    sys.planets.push(n);
  }
  systems.forEach(layoutSystem);
  systems.forEach(buildSun);
  for (const n of nodes.values()) if (!n.isSun) buildPlanet(n);
  for (const e of edges.values()) buildArc(e);
  buildFlyers();
  buildLegend();
  return ok.length;
}

// ---------- 图例即库存 ----------
function buildLegend() {
  const counts = {};
  for (const e of edges.values()) { const f = legendKey(e.relationship_family); counts[f] = (counts[f] || 0) + 1; }
  const list = document.getElementById("legend-list");
  list.innerHTML = "";
  for (const k of LEGEND_KEYS) {
    if (!counts[k]) continue;
    const li = document.createElement("li");
    li.innerHTML = `<button aria-pressed="true"><span class="swatch" style="color:${FAMILY[k].color}"></span><span>${FAMILY[k].zh}</span><span class="count">${fmt(counts[k])}</span></button>`;
    li.firstChild.addEventListener("click", (ev) => {
      const b = ev.currentTarget;
      const on = b.getAttribute("aria-pressed") !== "false";
      b.setAttribute("aria-pressed", on ? "false" : "true");
      on ? hiddenFamilies.add(k) : hiddenFamilies.delete(k);
      applyVisibility();
    });
    list.appendChild(li);
  }
  const cross = arcs.filter((a) => a.cross).length;
  document.getElementById("legend-foot").innerHTML = `<span style="color:#ffc861">●</span> 金色长弧 = 跨公司关联 ${fmt(cross)} 条 · 本视图 ${fmt(nodes.size)} 个天体、${fmt(edges.size)} 条关系`;
}
function legendKey(f) { const k = famOf(f); return k === "board_governance" ? "governance_people" : k; }
function applyVisibility() {
  for (const arc of arcs) arc.line.visible = !hiddenFamilies.has(legendKey(arc.edge.relationship_family));
  for (const n of nodes.values()) {
    if (n.isSun || !n.obj) continue;
    n.hiddenByFamily = hiddenFamilies.has(legendKey(n.fam));
    n.obj.group.visible = !n.hiddenByFamily;
  }
}

// ---------- 脉搏：全库规模与新鲜度 ----------
async function loadPulse() {
  try {
    const p = await getJSON("/v1/meta/pulse");
    document.getElementById("kpi-entities").textContent = fmt(p.totals?.entities);
    document.getElementById("kpi-relationships").textContent = fmt(p.totals?.relationships);
    document.getElementById("kpi-events").textContent = fmt(p.totals?.events);
    const asOf = p.data_as_of ? new Date(p.data_as_of) : null;
    const today = p.added?.today || {};
    const when = asOf ? asOf.toLocaleString("zh-CN", { timeZone: "Australia/Sydney", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "未知";
    const ageH = asOf ? (Date.now() - asOf.getTime()) / 3.6e6 : 999;
    document.getElementById("pulse-foot").textContent = `数据截至 ${when}（悉尼）· 今日新增 ${fmt(today.events || 0)} 条申报事件 · 来源 SEC、GLEIF`;
    document.getElementById("live-dot").className = "live-dot " + (ageH < 26 ? "on" : "warn");
  } catch (e) {
    document.getElementById("pulse-foot").textContent = "全库统计暂时没取到，星图照常可看；稍后自动重试";
    document.getElementById("live-dot").className = "live-dot warn";
    setTimeout(loadPulse, 30000);
  }
}


// 按屏幕尺寸自动取景：把所有恒星装进画面
function universeFrame() {
  const c = new THREE.Vector3();
  systems.forEach((s) => c.add(s.sun.pos));
  c.divideScalar(Math.max(systems.length, 1));
  let r = 0;
  systems.forEach((s) => { r = Math.max(r, s.sun.pos.distanceTo(c) + 90); });
  const vfov = (camera.fov * Math.PI) / 180;
  const hfov = 2 * Math.atan(Math.tan(vfov / 2) * camera.aspect);
  const fit = Math.min(vfov, hfov);
  return { center: c, distance: (r / Math.sin(fit / 2)) * 0.82 };
}
// ---------- 相机飞行 ----------
let flight = null;
function flyTo(target, distance, duration = 2.2) {
  const from = { pos: camera.position.clone(), tgt: controls.target.clone() };
  const dir = camera.position.clone().sub(controls.target).normalize();
  if (dir.y < 0.25) dir.y = 0.35;
  dir.normalize();
  const to = { tgt: target.clone(), pos: target.clone().add(dir.multiplyScalar(distance)) };
  flight = { from, to, t0: clock.elapsedTime, dur: REDUCED ? 0.01 : duration };
  pauseTour();
}
const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
function updateFlight(now) {
  if (!flight) return;
  const k = Math.min(1, (now - flight.t0) / flight.dur), e = ease(k);
  camera.position.lerpVectors(flight.from.pos, flight.to.pos, e);
  // 中途抬高一点，产生「穿越」弧线
  camera.position.y += Math.sin(e * Math.PI) * flight.from.pos.distanceTo(flight.to.pos) * 0.12;
  controls.target.lerpVectors(flight.from.tgt, flight.to.tgt, e);
  if (k >= 1) flight = null;
}

// ---------- 聚焦与选中 ----------
let focusSys = null, selected = null, hovered = null;
function focusSystem(sys) {
  focusSys = sys;
  document.getElementById("btn-home").hidden = false;
  flyTo(sys.sun.pos, 150 + Math.sqrt(sys.planets.length) * 18);
  refreshEmphasis();
}
function goHome() {
  focusSys = null; selected = null;
  closeDetail();
  document.getElementById("btn-home").hidden = true;
  { const f = universeFrame(); flyTo(f.center, f.distance, 2.4); }
  refreshEmphasis();
}
function refreshEmphasis() {
  const lit = new Set();
  if (selected) { lit.add(selected.id); for (const id of selected.edges) { const e = edges.get(id); lit.add(e.subject_id); lit.add(e.object_id); } }
  for (const arc of arcs) {
    let dim = 1;
    if (selected) dim = selected.edges.has(arc.edge.id) ? 2.2 : 0.12;
    else if (focusSys) dim = arc.a.system === focusSys || arc.b.system === focusSys ? 1.3 : 0.25;
    arc.line.material.uniforms.uDim.value = dim;
  }
  for (const n of nodes.values()) {
    if (!n.obj) continue;
    let o = 1;
    if (selected) o = lit.has(n.id) ? 1 : 0.22;
    else if (focusSys) o = n.system === focusSys || n.isSun ? 1 : 0.35;
    if (n.isSun) { n.obj.glow.material.opacity = 0.8 * Math.max(o, 0.5); n.obj.rays.material.opacity = 0.42 * Math.max(o, 0.4); }
    else { n.obj.glow.material.opacity = 0.9 * o; n.obj.core.material.opacity = Math.max(o, 0.3); }
  }
}

// ---------- 详情卡：关系 + 官方原文 ----------
const detail = document.getElementById("detail"), detailBody = document.getElementById("detail-body");
function closeDetail() { detail.hidden = true; selected = null; refreshEmphasis(); }
document.getElementById("detail-close").addEventListener("click", closeDetail);
async function selectNode(n) {
  selected = n;
  refreshEmphasis();
  const sys = n.system;
  const fam = n.isSun ? null : FAMILY[legendKey(n.fam)];
  const rels = [...n.edges].map((id) => edges.get(id)).filter(Boolean);
  const kind = n.isSun ? `<span class="kind" style="color:#e0a843"><i></i>恒星 · 核心公司</span>` : `<span class="kind" style="color:${fam.color}"><i></i>${n.type === "person" ? "人物" : "公司"} · ${fam.zh}</span>`;
  const crossCount = rels.filter((e) => nodes.get(e.subject_id)?.system !== nodes.get(e.object_id)?.system).length;
  const head = `${kind}<h3>${escapeHTML(n.isSun ? `${n.zh}` : n.name)}</h3>
    <p class="legal">${escapeHTML(n.isSun ? n.name : n.raw !== n.name ? n.raw : "")}${!n.isSun && /[^\u0000-\u024f\s.,()&'-]/.test(n.raw || "") ? `（官方登记原名；属于 ${escapeHTML(sys.sun.zh)} 星系）` : ""}</p>
    <div class="stats"><div><b>${fmt(rels.length)}</b><span>条已核实关系</span></div>${crossCount ? `<div><b>${fmt(crossCount)}</b><span>条跨公司关联</span></div>` : ""}${n.isSun ? `<div><b>${fmt(sys.planets.length + sys.moons.length)}</b><span>颗行星与卫星</span></div>` : ""}</div>`;
  const shown = rels.slice(0, n.isSun ? 6 : 10);
  const relHTML = shown.map((e) => {
    const otherId = e.subject_id === n.id ? e.object_id : e.subject_id;
    const other = nodes.get(otherId);
    const tier = e.evidence_tier === "single_official" ? `<span class="badge">单一官方来源</span>` : e.evidence_count > 1 ? `<span class="badge multi">${e.evidence_count} 个来源</span>` : `<span class="badge">官方来源</span>`;
    const dir = e.subject_id === n.id ? `是 ${escapeHTML(other?.isSun ? other.zh : other?.short || "对方")} 的` : `${escapeHTML(other?.isSun ? other.zh : other?.short || "对方")} 是它的`;
    return `<div class="rel" data-rel="${e.id}"><div class="rel-head"><span class="rel-type">${dir}${relZh(e.relationship_type)}</span>${tier}</div><div class="evidence">正在取官方原文…</div></div>`;
  }).join("");
  const more = rels.length > shown.length ? `<p class="legal">另有 ${rels.length - shown.length} 条关系，在完整图谱里查看</p>` : "";
  detailBody.innerHTML = `${head}<h4>${n.isSun ? "关系样本（点行星看全部）" : "它的关系与官方原文"}</h4>${relHTML}${more}
    <div class="actions">${n.isSun && focusSys !== sys ? `<button id="act-enter">进入这个星系</button>` : ""}<a href="https://eei.linzezhang.com/?subject=${encodeURIComponent(n.id)}" target="_blank" rel="noopener">在完整图谱中打开 ↗</a></div>`;
  detail.hidden = false;
  document.getElementById("act-enter")?.addEventListener("click", () => focusSystem(sys));
  for (const e of shown) loadEvidence(e);
}
const evidenceCache = new Map();
async function loadEvidence(e) {
  const box = () => detailBody.querySelector(`[data-rel="${e.id}"] .evidence`);
  try {
    let ev = evidenceCache.get(e.id);
    if (!ev) { ev = await getJSON(`/v1/evidence/relationship/${encodeURIComponent(e.id)}`); evidenceCache.set(e.id, ev); }
    const first = ev.evidence?.[0];
    const el = box();
    if (!el) return;
    if (!first) { el.textContent = "官方原文链接暂缺"; return; }
    const date = first.document_date ? first.document_date.slice(0, 10) : "";
    const pub = first.publisher?.includes("Securities") ? "SEC" : first.publisher?.includes("GLEIF") || /gleif/i.test(first.source_url || "") ? "GLEIF" : first.publisher || "官方";
    el.innerHTML = `${escapeHTML(pub)}${date ? " · " + date : ""} · ${first.source_url ? `<a href="${escapeHTML(first.source_url)}" target="_blank" rel="noopener">查看原文 ↗</a>` : "无原文链接"}`;
  } catch {
    const el = box();
    if (el) el.textContent = "官方原文暂时没取到，稍后再点一次";
  }
}

// ---------- 交互 ----------
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let downAt = null;
function pick(ev) {
  const r = canvas.getBoundingClientRect();
  pointer.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(pickables.filter((m) => m.parent.visible), false);
  return hits.length ? hits[0].object.userData.node : null;
}
canvas.addEventListener("pointerdown", (ev) => { downAt = { x: ev.clientX, y: ev.clientY }; canvas.classList.add("dragging"); pauseTour(); });
canvas.addEventListener("pointerup", (ev) => {
  canvas.classList.remove("dragging");
  if (!downAt || Math.hypot(ev.clientX - downAt.x, ev.clientY - downAt.y) > 6) return;
  const n = pick(ev);
  if (!n) { if (selected) closeDetail(); return; }
  if (n.isSun && focusSys !== n.system) { focusSystem(n.system); selectNode(n); }
  else { selectNode(n); if (!n.isSun && focusSys !== n.system) focusSystem(n.system); }
});
canvas.addEventListener("pointermove", (ev) => {
  if (MOBILE) return;
  const n = pick(ev);
  if (n !== hovered) { hovered = n; canvas.classList.toggle("pointing", !!n); }
});
document.getElementById("btn-home").addEventListener("click", goHome);

let touring = !REDUCED, idleTimer = null;
const tourBtn = document.getElementById("btn-tour");
function setTour(on) { touring = on; controls.autoRotate = on; tourBtn.setAttribute("aria-pressed", on ? "true" : "false"); tourBtn.textContent = on ? "漫游中" : "开始漫游"; }
function pauseTour() {
  if (touring) setTour(false);
  clearTimeout(idleTimer);
  if (!REDUCED) idleTimer = setTimeout(() => { if (!selected && !flight) setTour(true); }, 12000);
}
tourBtn.addEventListener("click", () => { clearTimeout(idleTimer); setTour(!touring); });
setTour(!REDUCED);

// 搜索：在视图内就飞过去；不在就把它点亮成一颗新恒星
const searchInput = document.getElementById("search"), results = document.getElementById("search-results");
let searchTimer = null, searchSeq = 0;
searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  const q = searchInput.value.trim();
  if (q.length < 2) { results.hidden = true; return; }
  searchTimer = setTimeout(async () => {
    const seq = ++searchSeq;
    const local = [...nodes.values()].filter((n) => n.name.toLowerCase().includes(q.toLowerCase()) || (n.zh || "").includes(q)).slice(0, 5);
    let remote = [];
    try { remote = (await getJSON(`/v1/entities?q=${encodeURIComponent(q)}&limit=8`)).entities || []; } catch {}
    if (seq !== searchSeq) return;
    const seen = new Set(local.map((n) => n.id));
    const rows = [
      ...local.map((n) => ({ id: n.id, name: n.isSun ? `${n.zh} · ${n.short}` : n.name, tag: "在星图里" })),
      ...remote.filter((e) => !seen.has(e.id)).map((e) => ({ id: e.id, name: prettyName(e.canonical_name), tag: nodes.has(e.id) ? "在星图里" : "点亮它" })),
    ].slice(0, 9);
    results.innerHTML = rows.length ? rows.map((r) => `<li data-id="${r.id}"><span>${escapeHTML(r.name)}</span><span class="tag">${r.tag}</span></li>`).join("") : `<li class="empty">没找到「${escapeHTML(q)}」，换个英文名试试</li>`;
    results.hidden = false;
  }, 250);
});
results.addEventListener("click", async (ev) => {
  const li = ev.target.closest("li[data-id]");
  if (!li) return;
  results.hidden = true;
  searchInput.value = "";
  const id = li.dataset.id;
  if (nodes.has(id)) { const n = nodes.get(id); focusSystem(n.system); selectNode(n); return; }
  await igniteNewStar(id);
});
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") { results.hidden = true; if (selected) closeDetail(); else if (focusSys) goHome(); }
  if (ev.key === "/" && document.activeElement !== searchInput) { ev.preventDefault(); searchInput.focus(); }
});

async function igniteNewStar(id) {
  setState(true, "正在点亮这颗新恒星…");
  try {
    const g = await exploreGraph(id);
    const idx = systems.length;
    const sun = upsertNode({ id: g.focus.id, canonical_name: g.focus.canonical_name, entity_type: g.focus.entity_type });
    sun.isSun = true; sun.zh = shortName(g.focus.canonical_name);
    const sys = { index: idx, sun, planets: [], moons: [], ringRadii: [0, 0, 0, 0] };
    sun.system = sys; sun.pos.copy(sunPosition(idx)); systems.push(sys);
    const fresh = [];
    for (const n of g.nodes) { const had = nodes.has(n.id); const node = upsertNode(n); if (!had) fresh.push(node); }
    for (const e of g.edges) {
      if (edges.has(e.id)) continue;
      edges.set(e.id, { ...e });
      nodes.get(e.subject_id)?.edges.add(e.id);
      nodes.get(e.object_id)?.edges.add(e.id);
    }
    for (const n of fresh) {
      if (n.isSun) continue;
      const e = [...n.edges].map((x) => edges.get(x)).find((x) => x.subject_id === sun.id || x.object_id === sun.id) || edges.get([...n.edges][0]);
      n.system = sys; n.fam = famOf(e?.relationship_family); n.role = "planet"; sys.planets.push(n);
    }
    layoutSystem(sys);
    buildSun(sys);
    for (const n of fresh) if (!n.isSun) buildPlanet(n);
    for (const e of g.edges) if (!edges.get(e.id).arc) buildArc(edges.get(e.id));
    scene.remove(flyers.pts); buildFlyers(); buildLegend(); applyVisibility();
    setState(false);
    focusSystem(sys); selectNode(sun);
  } catch (e) {
    setState(true, "这颗恒星的数据暂时没取到，稍后再试");
    setTimeout(() => setState(false), 2600);
  }
}

// ---------- 标签：按优先级放置，互不重叠 ----------
const v = new THREE.Vector3();
let labelFrame = 0;
function updateLabels() {
  if (++labelFrame % 2) return;
  const W = innerWidth, H = innerHeight;
  const cands = [];
  const camDist = camera.position.distanceTo(controls.target);
  for (const n of nodes.values()) {
    if (!n.label) continue;
    const vis = n.obj.group.visible !== false;
    let pri = -1;
    if (n === selected) pri = 100;
    else if (n === hovered) pri = 90;
    else if (n.isSun) pri = 60 + Math.min(n.system.planets.length, 30);
    else if (selected && selected.edges.size && [...selected.edges].some((id) => { const e = edges.get(id); return e.subject_id === n.id || e.object_id === n.id; })) pri = 50;
    else if (focusSys && n.system === focusSys && camDist < 420) pri = 10 + Math.min(n.edges.size, 20);
    if (pri < 0 || !vis) { n.label.style.opacity = "0"; continue; }
    v.copy(n.obj.group.position).project(camera);
    if (v.z > 1 || v.x < -1.1 || v.x > 1.1 || v.y < -1.1 || v.y > 1.1) { n.label.style.opacity = "0"; continue; }
    const x = (v.x * 0.5 + 0.5) * W, y = (-v.y * 0.5 + 0.5) * H + (n.isSun ? n.obj.size * 0.9 * (600 / Math.max(camDist, 60)) + 10 : 10);
    cands.push({ n, x, y, pri });
  }
  cands.sort((a, b) => b.pri - a.pri);
  const placed = [];
  const hit = (r) => placed.some((p) => !(r.r < p.l || r.l > p.r || r.b < p.t || r.t > p.b));
  for (const c of cands) {
    const w = c.n.isSun ? Math.max(70, Math.min(12 + c.n.short.length * 6.6, 230)) : Math.min(9 + c.n.short.length * 7, 240), h = c.n.isSun ? 36 : 18;
    const tries = c.n.isSun ? [[0, 0], [0, -h - 34], [w / 2 + 26, -h / 2 - 8], [-w / 2 - 26, -h / 2 - 8], [0, 22]] : [[0, 0]];
    let ok = null;
    for (const [dx, dy] of tries) {
      let x = c.x + dx, y = c.y + dy;
      x = Math.min(Math.max(x, w / 2 + 8), W - w / 2 - 8);
      y = Math.min(Math.max(y, 8), H - h - 8);
      const r = { l: x - w / 2 - 4, r: x + w / 2 + 4, t: y - 2, b: y + h + 2 };
      if (!hit(r)) { ok = { x, y, r }; break; }
    }
    if (!ok && c.pri >= 90) { const x = Math.min(Math.max(c.x, w / 2 + 8), W - w / 2 - 8); ok = { x, y: c.y, r: { l: x - w / 2, r: x + w / 2, t: c.y, b: c.y + h } }; }
    if (!ok) { c.n.label.style.opacity = "0"; continue; }
    placed.push(ok.r);
    c.n.label.style.opacity = "1";
    c.n.label.classList.toggle("focus", c.pri >= 90);
    c.n.label.style.transform = `translate(${ok.x.toFixed(1)}px, ${ok.y.toFixed(1)}px) translate(-50%, 0)`;
  }
}

// ---------- 动画 ----------
let revealStart = null;
function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(clock.getDelta(), 0.05);
  const t = clock.elapsedTime;
  uTime.value = REDUCED ? 0 : t;
  updateFlight(t);
  controls.update();
  nebulae.rotation.y += dt * 0.004;
  dust.rotation.y -= dt * 0.006;
  // 天体：恒星呼吸、光芒慢转、行星公转
  for (const sys of systems) {
    const o = sys.sun.obj;
    if (!o) continue;
    const reveal = revealStart === null ? 1 : Math.min(1, Math.max(0, (t - revealStart - sys.index * 0.14) / 1.1));
    const s = ease(reveal);
    o.group.scale.setScalar(Math.max(s, 0.0001));
    if (!REDUCED) {
      o.rays.material.rotation = t * 0.05 + sys.index;
      o.halo.scale.setScalar(o.size * (4.6 + Math.sin(t * 0.9 + sys.index) * 0.5));
    }
    for (const p of sys.planets) {
      if (!p.obj) continue;
      if (!REDUCED && p.orbit) {
        const a = p.orbit.a + t * p.orbit.speed * 0.25;
        const local = new THREE.Vector3(Math.cos(a) * p.orbit.r, p.orbit.y, Math.sin(a) * p.orbit.r).applyQuaternion(sys.tilt);
        local.y = p.orbit.y;
        p.obj.group.position.copy(sys.sun.pos).add(local);
      }
      p.obj.group.scale.setScalar(Math.max(ease(Math.min(1, Math.max(0, reveal * 1.4 - 0.4))), 0.0001));
    }
    for (const m of sys.moons) {
      if (!m.obj || !m.host?.obj) continue;
      const a = m.moon.a + (REDUCED ? 0 : t * 0.35);
      m.obj.group.position.copy(m.host.obj.group.position).add(new THREE.Vector3(Math.cos(a) * m.moon.r, 1.2, Math.sin(a) * m.moon.r));
      m.obj.group.scale.setScalar(Math.max(ease(Math.min(1, Math.max(0, reveal * 1.4 - 0.5))), 0.0001));
    }
  }
  if (!REDUCED && arcs.length) refreshArcGeometry();
  updateFlyers(t);
  updateLabels();
  composer.render();
}
// 行星在转，光弧端点跟着走（每 3 帧更新一次，省力）
let arcFrame = 0;
function refreshArcGeometry() {
  if (++arcFrame % 3) return;
  for (const arc of arcs) {
    if (!arc.line.visible) continue;
    const a = arc.a.obj?.group.position, b = arc.b.obj?.group.position;
    if (!a || !b) continue;
    const pts = curvePoints(a, b, arc.cross ? 0.32 : 0.18, arc.pts.length - 1);
    arc.pts = pts;
    const attr = arc.line.geometry.attributes.position;
    for (let i = 0; i < pts.length; i++) attr.setXYZ(i, pts[i].x, pts[i].y, pts[i].z);
    attr.needsUpdate = true;
  }
}

addEventListener("resize", () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
  composer.setSize(innerWidth, innerHeight);
  bloom.setSize(innerWidth, innerHeight);
});

// ---------- 状态层 ----------
const stateEl = document.getElementById("state"), stateText = document.getElementById("state-text");
function setState(on, text) { if (text) stateText.textContent = text; stateEl.classList.toggle("gone", !on); }

async function boot() {
  animate();
  loadPulse();
  setInterval(loadPulse, 5 * 60 * 1000);
  let attempt = 0;
  while (true) {
    try {
      const n = await loadUniverse();
      setState(false);
      revealStart = clock.elapsedTime + 0.3;
      { const f = universeFrame(); flyTo(f.center, f.distance, REDUCED ? 0.01 : 4.2); }
      setTimeout(() => { if (!selected) setTour(!REDUCED); }, 4600);
      setTimeout(() => { document.getElementById("hint").style.opacity = "0"; }, 14000);
      window.__universe = { suns: n, nodes: nodes.size, edges: edges.size, cross: arcs.filter((a) => a.cross).length, systems: systems.map((s) => [s.sun.zh, s.planets.length, s.moons.length, s.nodeCount, s.edgeCount]) };
      return;
    } catch (e) {
      attempt++;
      const wait = Math.min(60, 5 * attempt);
      setState(true, `官方数据接口暂时连不上（${e.message}）。${wait} 秒后自动重试…`);
      await new Promise((r) => setTimeout(r, wait * 1000));
    }
  }
}
boot();
