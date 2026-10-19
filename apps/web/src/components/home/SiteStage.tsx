"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { fetchProjects } from "@/lib/api";
import type { Locale } from "@/lib/types";

type Layer = "concrete" | "rebar" | "mep" | "estimate" | "ks";
type ViewMode = "section" | "plan" | "site";

const VIEWS: Record<ViewMode, { pos: [number, number, number]; target: [number, number, number] }> = {
  section: { pos: [36, 18.5, 34], target: [0, 6.2, 1] },
  plan: { pos: [2, 36, 14], target: [0.2, 8, 0] },
  site: { pos: [42, 26, 40], target: [0, 6, -1] },
};

type Health = "green" | "amber" | "red";

type SiteSnap = {
  project: { id: string; title: string; address: string; status: string };
  health: Health;
  budget_kzt: number;
  actual_kzt: number;
  committed_kzt: number;
  open_rfi: number;
  open_punch: number;
  open_incidents: number;
  counts: { daily: number; drawings: number; inspections: number };
};

const HEALTH_HEX: Record<Health, number> = {
  green: 0x7dcea0,
  amber: 0xe2b657,
  red: 0xe07a68,
};

const copy = {
  ru: {
    kicker: "Площадки онлайн",
    live: "Сводка площадок",
    waiting: "Ждём ответ площадок",
    empty: "Площадок пока нет",
    failed: "Не удалось обновить. Повторим сами.",
    budget: "Бюджет",
    actual: "Факт",
    committed: "Законтрактовано",
    rfi: "Открытые RFI",
    punch: "Дефекты",
    drawings: "Чертежи",
    open: "Открыть эту площадку",
    updated: "обновлено",
    sites: "объектов",
    canvas: "Живой разрез стройплощадки ANYQ. Прокрутка закрывает фасад выбранного объекта.",
  },
  kk: {
    kicker: "Алаңдар онлайн",
    live: "Алаңдар жинағы",
    waiting: "Алаң жауабын күтеміз",
    empty: "Алаңдар әлі жоқ",
    failed: "Жаңарту сәтсіз. Қайталап көреміз.",
    budget: "Бюджет",
    actual: "Нақты",
    committed: "Келісімшарт",
    rfi: "Ашық RFI",
    punch: "Ақаулар",
    drawings: "Сызбалар",
    open: "Осы алаңды ашу",
    updated: "жаңартылды",
    sites: "нысан",
    canvas: "ANYQ құрылыс алаңының тірі қимасы. Сырғытсаңыз таңдалған нысанның қасбеті жабылады.",
  },
};

function tenge(n: number) {
  if (n >= 1_000_000) {
    const v = n / 1_000_000;
    const text = v >= 10 ? String(Math.round(v)) : v.toFixed(1).replace(".", ",");
    return `${text} млн ₸`;
  }
  return `${new Intl.NumberFormat("ru-KZ").format(n)} ₸`;
}

function clock(d: Date) {
  return d.toLocaleTimeString("ru-KZ", { hour: "2-digit", minute: "2-digit" });
}

function smoother(edge0: number, edge1: number, x: number) {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

function mergeGeos(geos: THREE.BufferGeometry[]) {
  let verts = 0;
  for (const geo of geos) verts += geo.getAttribute("position").count;
  const position = new Float32Array(verts * 3);
  const normal = new Float32Array(verts * 3);
  const hasUv = geos.every((geo) => geo.getAttribute("uv"));
  const uv = hasUv ? new Float32Array(verts * 2) : null;
  let cursor = 0;
  let uvCursor = 0;
  for (const geo of geos) {
    const p = geo.getAttribute("position");
    const n = geo.getAttribute("normal");
    position.set(p.array as ArrayLike<number>, cursor);
    normal.set(n.array as ArrayLike<number>, cursor);
    if (uv) {
      const u = geo.getAttribute("uv");
      uv.set(u.array as ArrayLike<number>, uvCursor);
      uvCursor += u.count * 2;
    }
    cursor += p.count * 3;
    geo.dispose();
  }
  const merged = new THREE.BufferGeometry();
  merged.setAttribute("position", new THREE.BufferAttribute(position, 3));
  merged.setAttribute("normal", new THREE.BufferAttribute(normal, 3));
  if (uv) merged.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
  return merged;
}

function stageBackground(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const g = canvas.getContext("2d");
  if (!g) return new THREE.CanvasTexture(canvas);
  const sky = g.createLinearGradient(0, 0, 0, 512);
  sky.addColorStop(0, "#08111d");
  sky.addColorStop(0.38, "#16304c");
  sky.addColorStop(0.62, "#8d7358");
  sky.addColorStop(0.74, "#1b2838");
  sky.addColorStop(1, "#101722");
  g.fillStyle = sky;
  g.fillRect(0, 0, 512, 512);
  const glow = g.createRadialGradient(360, 250, 8, 360, 268, 220);
  glow.addColorStop(0, "rgba(255, 214, 170, 0.55)");
  glow.addColorStop(0.28, "rgba(255, 176, 110, 0.16)");
  glow.addColorStop(1, "rgba(255, 176, 110, 0)");
  g.fillStyle = glow;
  g.fillRect(0, 0, 512, 512);
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function contactShadow(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  const g = canvas.getContext("2d");
  if (!g) return new THREE.CanvasTexture(canvas);
  const grd = g.createRadialGradient(64, 64, 8, 64, 64, 64);
  grd.addColorStop(0, "rgba(0,0,0,0.55)");
  grd.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grd;
  g.fillRect(0, 0, 128, 128);
  const tex = new THREE.CanvasTexture(canvas);
  return tex;
}

function skyEnvironment() {
  const scene = new THREE.Scene();
  const shell = new THREE.Mesh(new THREE.BoxGeometry(24, 24, 24), [
    new THREE.MeshBasicMaterial({ color: "#7ea4c4", side: THREE.BackSide }),
    new THREE.MeshBasicMaterial({ color: "#16324a", side: THREE.BackSide }),
    new THREE.MeshBasicMaterial({ color: "#e7f1f8", side: THREE.BackSide }),
    new THREE.MeshBasicMaterial({ color: "#12161c", side: THREE.BackSide }),
    new THREE.MeshBasicMaterial({ color: "#f3c9a2", side: THREE.BackSide }),
    new THREE.MeshBasicMaterial({ color: "#2a4660", side: THREE.BackSide }),
  ]);
  scene.add(shell);
  return scene;
}

function concreteGrit(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const g = canvas.getContext("2d");
  const tex = new THREE.CanvasTexture(canvas);
  if (!g) return tex;
  g.fillStyle = "#c9c3b8";
  g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 2200; i++) {
    const v = 70 + Math.random() * 90;
    g.fillStyle = `rgba(${v},${v - 6},${v - 12},${0.06 + Math.random() * 0.16})`;
    g.fillRect(Math.random() * 256, Math.random() * 256, 1 + Math.random() * 2, 1 + Math.random() * 2);
  }
  g.strokeStyle = "rgba(40, 36, 32, 0.22)";
  g.lineWidth = 1;
  for (let y = 8; y < 256; y += 28) {
    g.beginPath();
    g.moveTo(0, y);
    g.lineTo(256, y);
    g.stroke();
  }
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(3, 3);
  return tex;
}

function padTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const g = canvas.getContext("2d");
  const tex = new THREE.CanvasTexture(canvas);
  if (!g) return tex;
  g.fillStyle = "#1c2430";
  g.fillRect(0, 0, 512, 512);
  g.strokeStyle = "rgba(180, 198, 214, 0.16)";
  g.lineWidth = 1;
  for (let i = 0; i <= 512; i += 32) {
    g.beginPath();
    g.moveTo(i, 0);
    g.lineTo(i, 512);
    g.stroke();
    g.beginPath();
    g.moveTo(0, i);
    g.lineTo(512, i);
    g.stroke();
  }
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

export function SiteStage({ locale }: { locale: Locale }) {
  const t = locale === "kk" ? copy.kk : copy.ru;
  const trackRef = useRef<HTMLElement>(null);
  const pinRef = useRef<HTMLDivElement>(null);
  const hostRef = useRef<HTMLDivElement>(null);
  const uiRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef(0);
  const driveRef = useRef<{ health: Health }>({ health: "green" });
  const syncUiRef = useRef<(p: number) => void>(() => {});
  const [ready, setReady] = useState(false);
  const [snaps, setSnaps] = useState<SiteSnap[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [updated, setUpdated] = useState<Date | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [reducedMotion] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    syncUiRef.current(scrollRef.current);
  }, [ready]);

  useEffect(() => {
    let stop = false;
    async function pull() {
      if (document.hidden) return;
      if (!localStorage.getItem("superapp_token")) {
        setSnaps([]);
        setSelected(null);
        setLoadState("ready");
        return;
      }
      try {
        const rows = (await fetchProjects()) as unknown as SiteSnap[];
        if (stop) return;
        setSnaps(rows);
        setSelected((cur) => (cur && rows.some((row) => row.project.id === cur) ? cur : rows[0]?.project.id ?? null));
        setUpdated(new Date());
        setLoadState("ready");
      } catch {
        if (!stop) setLoadState((prev) => (prev === "ready" ? "ready" : "error"));
      }
    }
    pull();
    const timer = window.setInterval(pull, 12000);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, []);

  const active = snaps.find((row) => row.project.id === selected) ?? snaps[0] ?? null;
  useEffect(() => {
    driveRef.current.health = active?.health ?? "green";
  }, [active]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const stage: HTMLDivElement = host;
    let cancelled = false;
    let raf = 0;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const scene = new THREE.Scene();
    scene.background = stageBackground();
    scene.fog = new THREE.FogExp2(0x101722, 0.0035);

    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 220);
    const start = VIEWS.section;
    const desiredPos = new THREE.Vector3(...start.pos);
    const desiredTarget = new THREE.Vector3(...start.target);
    const camPos = desiredPos.clone();
    const camTarget = desiredTarget.clone();
    camera.position.copy(camPos);

    const renderer = new THREE.WebGLRenderer({
      antialias: (window.devicePixelRatio || 1) <= 1.25,
      alpha: false,
      stencil: false,
      powerPreference: "high-performance",
    });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.shadowMap.enabled = false;
    renderer.setClearColor(0x101726, 1);
    stage.appendChild(renderer.domElement);
    renderer.domElement.style.display = "block";
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";

    const pmrem = new THREE.PMREMGenerator(renderer);
    const envMap = pmrem.fromScene(skyEnvironment(), 0.04).texture;
    scene.environment = envMap;
    scene.environmentIntensity = 1;
    pmrem.dispose();

    const hemi = new THREE.HemisphereLight(0xb7c6d6, 0x1a140e, 0.48);
    scene.add(hemi);

    const sun = new THREE.DirectionalLight(0xfff1dd, 3.4);
    sun.position.set(18, 26, 10);
    sun.target.position.set(0, 6, 0);
    scene.add(sun);
    scene.add(sun.target);

    const interiorGlow = new THREE.PointLight(0xffb06a, 46, 32, 2);
    interiorGlow.position.set(-3.4, 9.2, 0.2);
    scene.add(interiorGlow);

    const grit = concreteGrit();
    const concreteMats: THREE.MeshStandardMaterial[] = [];
    const makeConcrete = (color: string) => {
      const mat = new THREE.MeshStandardMaterial({
        color,
        map: grit,
        roughness: 0.58,
        metalness: 0.04,
        envMapIntensity: 0.42,
      });
      concreteMats.push(mat);
      return mat;
    };
    const slabMat = makeConcrete("#5e5a54");
    const colMat = makeConcrete("#4a4642");
    const raftMat = makeConcrete("#3a3633");
    const skinMat = new THREE.MeshStandardMaterial({
      color: "#5e5a54",
      map: grit,
      roughness: 0.58,
      metalness: 0.04,
      envMapIntensity: 0.42,
    });
    const woodMat = new THREE.MeshStandardMaterial({
      color: "#8a6234",
      roughness: 0.82,
      metalness: 0.02,
      transparent: true,
      opacity: 1,
    });
    const rebarMat = new THREE.MeshStandardMaterial({ color: "#8d949c", roughness: 0.28, metalness: 0.92, envMapIntensity: 1.1 });
    const steelMat = new THREE.MeshStandardMaterial({ color: "#d5dbe0", roughness: 0.22, metalness: 0.86, envMapIntensity: 1.35 });
    const jibMat = new THREE.MeshStandardMaterial({ color: "#c6a15b", roughness: 0.34, metalness: 0.72, envMapIntensity: 1.1 });
    const groundMat = new THREE.MeshStandardMaterial({ color: "#141922", roughness: 1, metalness: 0 });
    const padTex = padTexture();
    const padMat = new THREE.MeshStandardMaterial({
      map: padTex,
      color: "#c5d0dc",
      roughness: 0.92,
      metalness: 0.04,
    });
    const cabinA = new THREE.MeshStandardMaterial({ color: "#cbb89a", roughness: 0.8, metalness: 0.02 });
    const cabinB = new THREE.MeshStandardMaterial({ color: "#3c4a43", roughness: 0.8, metalness: 0.04 });
    const fenceMat = new THREE.MeshStandardMaterial({ color: "#3a424c", roughness: 0.7, metalness: 0.2 });
    const mepMats = [
      new THREE.MeshStandardMaterial({ color: "#b55248", roughness: 0.4, metalness: 0.35 }),
      new THREE.MeshStandardMaterial({ color: "#3d6d99", roughness: 0.4, metalness: 0.35 }),
      new THREE.MeshStandardMaterial({ color: "#c2b8aa", roughness: 0.45, metalness: 0.25 }),
    ];
    mepMats.forEach((m) => {
      m.transparent = true;
      m.opacity = 0.22;
    });
    const ringMat = new THREE.MeshStandardMaterial({
      color: "#9eb6d0",
      emissive: "#6e8eae",
      emissiveIntensity: 0.2,
      roughness: 0.4,
      metalness: 0.1,
      transparent: true,
      opacity: 0.35,
    });

    const concrete = new THREE.Group();
    const skin = new THREE.Group();
    const works = new THREE.Group();
    const rebarHero = new THREE.Group();
    const rebarDeep = new THREE.Group();
    const mep = new THREE.Group();
    const site = new THREE.Group();
    scene.add(concrete, skin, works, rebarHero, rebarDeep, mep, site);
    skin.visible = true;
    rebarDeep.visible = false;

    const tracked: THREE.Mesh[] = [];

    function addBox(
      parent: THREE.Object3D,
      mat: THREE.Material,
      size: [number, number, number],
      pos: [number, number, number],
      floor?: number,
      shadow = false,
    ) {
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(size[0], size[1], size[2]), mat);
      mesh.position.set(pos[0], pos[1], pos[2]);
      if (floor !== undefined) mesh.userData.floor = floor;
      mesh.castShadow = shadow;
      mesh.receiveShadow = shadow;
      parent.add(mesh);
      tracked.push(mesh);
      return mesh;
    }

    function addCyl(
      parent: THREE.Object3D,
      mat: THREE.Material,
      radius: number,
      length: number,
      pos: [number, number, number],
      axis: "x" | "y" | "z",
      floor?: number,
    ) {
      const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, length, 8), mat);
      mesh.position.set(pos[0], pos[1], pos[2]);
      if (axis === "x") mesh.rotation.z = Math.PI / 2;
      if (axis === "z") mesh.rotation.x = Math.PI / 2;
      if (floor !== undefined) mesh.userData.floor = floor;
      parent.add(mesh);
      tracked.push(mesh);
      return mesh;
    }

    // Open corner faces the camera (x > 1.2 and z > -0.5) so the frame reads as a cutaway.
    const SLAB_T = 0.24;
    const levels = [
      { floor: 1, y: 3.2 },
      { floor: 2, y: 6.35 },
      { floor: 3, y: 9.5 },
      { floor: 4, y: 12.65 },
      { floor: 5, y: 15.8 },
    ];

    addBox(concrete, raftMat, [19.6, 0.5, 15.6], [0, 0.2, 0], -1, true);

    function addSlab(parent: THREE.Object3D, floor: number, y: number) {
      const cy = y + SLAB_T / 2;
      addBox(parent, slabMat, [10.2, SLAB_T, 14], [-3.9, cy, 0], floor, true);
      addBox(parent, slabMat, [7.8, SLAB_T, 6.5], [5.1, cy, -3.75], floor, true);
    }

    levels.forEach((level) => addSlab(concrete, level.floor, level.y));

    const interior = new THREE.Group();
    scene.add(interior);
    const oak = new THREE.MeshStandardMaterial({ color: "#8d7054", roughness: 0.4, metalness: 0.06, envMapIntensity: 0.5 });
    const walnut = new THREE.MeshStandardMaterial({ color: "#5c3b2a", roughness: 0.38, metalness: 0.08, envMapIntensity: 0.55 });
    const linen = new THREE.MeshStandardMaterial({ color: "#e6e0d6", roughness: 0.62, metalness: 0.02 });
    const ink = new THREE.MeshStandardMaterial({ color: "#242a30", roughness: 0.45, metalness: 0.12, envMapIntensity: 0.7 });
    const slate = new THREE.MeshStandardMaterial({ color: "#d9d4cc", roughness: 0.5, metalness: 0.04 });
    const screenMat = new THREE.MeshStandardMaterial({
      color: "#9fd4ff",
      emissive: "#7ec8ff",
      emissiveIntensity: 1.6,
      roughness: 0.18,
      metalness: 0.05,
    });
    const leaf = new THREE.MeshStandardMaterial({ color: "#2f6a45", roughness: 0.72, metalness: 0 });
    const potMat = new THREE.MeshStandardMaterial({ color: "#efe8de", roughness: 0.48, metalness: 0.04 });
    const barMat = new THREE.MeshStandardMaterial({
      color: "#fff4e4",
      emissive: "#ffe7c2",
      emissiveIntensity: 2.4,
      roughness: 0.25,
    });
    const trim = new THREE.MeshStandardMaterial({ color: "#171b1f", roughness: 0.28, metalness: 0.78, envMapIntensity: 1.2 });

    function plantAt(x: number, z: number, y: number, floor: number) {
      addCyl(interior, potMat, 0.16, 0.22, [x, y + 0.11, z], "y", floor);
      addCyl(interior, leaf, 0.28, 0.42, [x, y + 0.42, z], "y", floor);
      addCyl(interior, leaf, 0.18, 0.28, [x, y + 0.72, z], "y", floor);
    }

    const skinTones = ["#e4b89a", "#c9865a", "#8d5a3b", "#f0c7a8"].map(
      (color) => new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.02 }),
    );
    const coats = ["#1e3348", "#3d342c", "#24362c", "#4a3b34", "#2a3140"].map(
      (color) => new THREE.MeshStandardMaterial({ color, roughness: 0.62, metalness: 0.04 }),
    );
    let personN = 0;

    function addSphere(
      parent: THREE.Object3D,
      mat: THREE.Material,
      radius: number,
      pos: [number, number, number],
      floor?: number,
    ) {
      const mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, 8, 6), mat);
      mesh.position.set(pos[0], pos[1], pos[2]);
      if (floor !== undefined) mesh.userData.floor = floor;
      parent.add(mesh);
      tracked.push(mesh);
      return mesh;
    }

    function compact(root: THREE.Object3D) {
      root.updateWorldMatrix(true, true);
      const inv = new THREE.Matrix4().copy(root.matrixWorld).invert();
      const bake = new THREE.Matrix4();
      type Bucket = { mat: THREE.Material; geos: THREE.BufferGeometry[]; floor?: number };
      const buckets = new Map<string, Bucket>();
      const old: THREE.Mesh[] = [];
      root.traverse((obj) => {
        const mesh = obj as THREE.Mesh;
        if (!mesh.isMesh || !mesh.geometry || Array.isArray(mesh.material)) return;
        old.push(mesh);
        const floor = mesh.userData.floor as number | undefined;
        const key = `${mesh.material.uuid}|${floor ?? "x"}`;
        let bucket = buckets.get(key);
        if (!bucket) {
          bucket = { mat: mesh.material, geos: [], floor };
          buckets.set(key, bucket);
        }
        const geo = mesh.geometry.index ? mesh.geometry.toNonIndexed() : mesh.geometry.clone();
        bake.multiplyMatrices(inv, mesh.matrixWorld);
        geo.applyMatrix4(bake);
        bucket.geos.push(geo);
      });
      const drop = new Set(old);
      for (let i = tracked.length - 1; i >= 0; i--) {
        if (drop.has(tracked[i])) tracked.splice(i, 1);
      }
      for (const mesh of old) {
        mesh.removeFromParent();
        mesh.geometry.dispose();
      }
      for (const bucket of buckets.values()) {
        const geo = bucket.geos.length === 1 ? bucket.geos[0] : mergeGeos(bucket.geos);
        const mesh = new THREE.Mesh(geo, bucket.mat);
        if (bucket.floor !== undefined) mesh.userData.floor = bucket.floor;
        root.add(mesh);
        tracked.push(mesh);
      }
    }

    function person(x: number, z: number, y: number, floor: number, seated: boolean) {
      const coat = coats[personN % coats.length];
      const skin = skinTones[personN % skinTones.length];
      personN += 1;
      const legH = seated ? 0.22 : 0.72;
      const hip = y + (seated ? 0.46 : 0.78);
      addBox(interior, ink, [0.1, legH, 0.1], [x - 0.07, y + legH / 2, z], floor);
      addBox(interior, ink, [0.1, legH, 0.1], [x + 0.07, y + legH / 2, z], floor);
      addBox(interior, coat, [0.34, 0.46, 0.18], [x, hip + 0.18, z], floor);
      addSphere(interior, skin, 0.11, [x, hip + 0.5, z], floor);
    }

    function deskAt(x: number, z: number, y: number, floor: number, face: 1 | -1) {
      addBox(interior, slate, [1.35, 0.05, 0.62], [x, y + 0.74, z], floor);
      addBox(interior, trim, [1.2, 0.68, 0.04], [x, y + 0.36, z - face * 0.26], floor);
      addBox(interior, ink, [0.42, 0.42, 0.42], [x - face * 0.15, y + 0.42, z + face * 0.38], floor);
      addBox(interior, ink, [0.04, 0.38, 0.42], [x - face * 0.15, y + 0.78, z + face * 0.55], floor);
      addBox(interior, screenMat, [0.46, 0.3, 0.02], [x + 0.28, y + 0.98, z], floor);
      addBox(interior, trim, [0.08, 0.12, 0.08], [x + 0.28, y + 0.8, z], floor);
    }

    levels.forEach((level) => {
      const y = level.y + SLAB_T;
      const floor = level.floor;
      addBox(interior, oak, [9.7, 0.045, 13.4], [-3.9, y + 0.03, 0], floor);
      [-5.2, -1.6, 2, 5.2].forEach((z) => {
        addBox(interior, barMat, [6.4, 0.035, 0.08], [-3.8, y + 2.55, z], floor);
      });
      addBox(interior, linen, [0.1, 2.35, 4.2], [-0.4, y + 1.2, -3.6], floor);
      addBox(interior, linen, [2.4, 2.35, 0.1], [-1.6, y + 1.2, -5.6], floor);
      plantAt(-8.2, 5.6, y, floor);
      plantAt(-8.2, -5.8, y, floor);

      if (floor === 1) {
        addBox(interior, walnut, [2.4, 0.08, 0.7], [-6.2, y + 1.05, 1.2], floor);
        addBox(interior, trim, [2.2, 1.0, 0.08], [-6.2, y + 0.52, 0.82], floor);
        addBox(interior, ink, [1.5, 0.42, 0.62], [-6.4, y + 0.28, 3.5], floor);
        addBox(interior, ink, [1.5, 0.5, 0.1], [-6.4, y + 0.7, 3.78], floor);
        addBox(interior, ink, [1.5, 0.42, 0.62], [-6.4, y + 0.28, 5.15], floor);
        addBox(interior, ink, [1.5, 0.5, 0.1], [-6.4, y + 0.7, 4.86], floor);
        addBox(interior, walnut, [0.7, 0.04, 0.7], [-4.2, y + 0.4, 4.3], floor);
        addBox(interior, trim, [0.06, 0.38, 0.06], [-4.45, y + 0.2, 4.05], floor);
        addBox(interior, trim, [0.06, 0.38, 0.06], [-3.95, y + 0.2, 4.55], floor);
        plantAt(-4.6, 1.4, y, floor);
        person(-5.1, 4.15, y, floor, true);
        person(-7.6, 4.15, y, floor, true);
        person(-6.6, 2.15, y, floor, false);
        person(-4.8, 2.35, y, floor, false);
      } else if (floor === 5) {
        addBox(interior, walnut, [3.2, 0.07, 1.15], [-5.4, y + 0.76, 1.6], floor);
        addBox(interior, trim, [2.8, 0.7, 0.08], [-5.4, y + 0.38, 1.6], floor);
        [-0.9, 0.9].forEach((side) => {
          [-1.15, 0, 1.15].forEach((along) => {
            addBox(interior, ink, [0.42, 0.4, 0.42], [-5.4 + along, y + 0.28, 1.6 + side], floor);
            addBox(interior, ink, [0.42, 0.42, 0.06], [-5.4 + along, y + 0.66, 1.6 + side * 1.18], floor);
          });
        });
        addBox(interior, linen, [1.6, 0.4, 0.7], [-2.2, y + 0.28, 4.6], floor);
        addBox(interior, linen, [1.6, 0.45, 0.08], [-2.2, y + 0.68, 4.9], floor);
        plantAt(-2.4, -1.2, y, floor);
        [-1.15, 0, 1.15].forEach((along, index) => {
          person(-5.4 + along, 0.55, y, floor, true);
          if (index !== 1) person(-5.4 + along, 2.65, y, floor, true);
        });
        person(-2.6, 4.35, y, floor, true);
      } else {
        let seat = 0;
        [-7.1, -5.2, -3.3].forEach((x) => {
          [-4.4, -2.2, 0.4, 3.2].forEach((z) => {
            deskAt(x, z, y, floor, 1);
            if (seat % 2 === 0) person(x - 0.15, z + 0.55, y, floor, true);
            seat += 1;
          });
        });
        addBox(interior, linen, [0.08, 1.35, 6.4], [-4.25, y + 0.7, -1.2], floor);
      }
    });
    levels.forEach((level) => {
      const cy = level.y + SLAB_T / 2;
      const plate = addBox(skin, skinMat, [7.8, SLAB_T, 7.5], [5.1, cy, 3.25], level.floor, true);
      plate.visible = false;
    });

    const xs = [-7.2, -3.6, 0, 3.6, 7.2];
    const zs = [-5.2, -1.6, 2, 5.2];
    const columnSpans: { y0: number; y1: number; floor: number }[] = [
      { y0: 0.46, y1: levels[0].y, floor: 1 },
    ];
    for (let i = 0; i < levels.length - 1; i++) {
      columnSpans.push({
        y0: levels[i].y + SLAB_T,
        y1: levels[i + 1].y,
        floor: levels[i + 1].floor,
      });
    }

    xs.forEach((x) => {
      zs.forEach((z) => {
        const exposed = x > 1.2 && z > -0.5;
        columnSpans.forEach((span) => {
          const h = span.y1 - span.y0;
          const py = (span.y0 + span.y1) / 2;
          addBox(concrete, colMat, [0.42, h, 0.42], [x, py, z], span.floor, true);
          if (exposed && span.floor >= 4) {
            const parent = span.floor === 5 ? rebarHero : rebarDeep;
            const inset = 0.12;
            ([
              [x - inset, z - inset],
              [x + inset, z - inset],
              [x - inset, z + inset],
              [x + inset, z + inset],
            ] as const).forEach(([bx, bz]) => {
              addCyl(parent, rebarMat, 0.028, h, [bx, py, bz], "y", span.floor);
            });
          }
        });
        if (exposed) {
          addCyl(rebarHero, rebarMat, 0.03, 1.5, [x - 0.12, 16.85, z - 0.12], "y", 5);
          addCyl(rebarHero, rebarMat, 0.03, 1.5, [x + 0.12, 16.85, z - 0.12], "y", 5);
          addCyl(rebarHero, rebarMat, 0.03, 1.5, [x - 0.12, 16.85, z + 0.12], "y", 5);
          addCyl(rebarHero, rebarMat, 0.03, 1.5, [x + 0.12, 16.85, z + 0.12], "y", 5);
        }
      });
    });

    for (let i = 0; i < 7; i++) {
      addCyl(rebarHero, rebarMat, 0.018, 7.3, [5.1, 16.12, -0.15 + i * 1.15], "x", 5);
    }
    for (let i = 0; i < 6; i++) {
      addCyl(rebarHero, rebarMat, 0.018, 7.1, [1.7 + i * 1.25, 16.18, 3.25], "z", 5);
    }

    addBox(works, woodMat, [0.08, 0.55, 14], [1.24, 16.3, 0], 5);
    addBox(works, woodMat, [7.8, 0.55, 0.08], [5.1, 16.3, -0.46], 5);
    [2.4, 4.2, 6.0, 7.6].forEach((x) => {
      [1.1, 3.2, 5.2].forEach((z) => {
        addCyl(works, woodMat, 0.055, 2.9, [x, 14.3, z], "y", 5);
      });
    });

    for (let s = 0; s < 16; s++) {
      const y = 3.5 + s * 0.175;
      addBox(concrete, slabMat, [1.15, 0.07, 0.28], [2.15, y, 0.35 + s * 0.28], 3);
    }

    const pipeX = [2.35, 2.7, 3.05];
    columnSpans.forEach((span) => {
      const h = span.y1 - span.y0;
      const py = (span.y0 + span.y1) / 2;
      pipeX.forEach((x, i) => {
        addCyl(mep, mepMats[i], 0.07, h, [x, py, 1.15], "y", span.floor);
      });
    });

    const ring = new THREE.Group();
    scene.add(ring);
    addBox(ring, ringMat, [18.4, 0.05, 0.08], [0, 0, -7.15]);
    addBox(ring, ringMat, [18.4, 0.05, 0.08], [0, 0, 7.15]);
    addBox(ring, ringMat, [0.08, 0.05, 14.3], [-9.15, 0, 0]);
    addBox(ring, ringMat, [0.08, 0.05, 14.3], [9.15, 0, 0]);

    const shadowTex = contactShadow();
    const shadow = new THREE.Mesh(
      new THREE.PlaneGeometry(34, 28),
      new THREE.MeshBasicMaterial({ map: shadowTex, transparent: true, depthWrite: false }),
    );
    shadow.rotation.x = -Math.PI / 2;
    shadow.position.y = 0.02;
    site.add(shadow);

    addBox(site, groundMat, [70, 0.2, 60], [0, -0.12, 0], undefined, true);
    addBox(site, padMat, [24, 0.08, 20], [0, 0.02, 0]);

    const crane = new THREE.Group();
    crane.position.set(-1.5, 0, -13.2);
    site.add(crane);
    addBox(crane, steelMat, [0.55, 22, 0.55], [0, 11, 0], undefined, true);
    addBox(crane, steelMat, [1.3, 0.4, 1.3], [0, 22.1, 0]);
    addBox(crane, jibMat, [16, 0.22, 0.38], [8.2, 22.45, 0]);
    addBox(crane, steelMat, [5.2, 0.2, 0.36], [-2.8, 22.4, 0]);
    addBox(crane, colMat, [1.3, 0.7, 0.8], [-5.1, 22.1, 0]);
    const hook = new THREE.Group();
    hook.position.set(11.5, 18.4, 0);
    crane.add(hook);
    addCyl(hook, steelMat, 0.012, 7.2, [0, 1.6, 0], "y");
    addBox(hook, steelMat, [0.28, 0.36, 0.28], [0, -2.15, 0]);

    const yard = new THREE.Group();
    site.add(yard);
    addBox(yard, cabinA, [4.2, 2.5, 2.3], [-14.5, 1.35, -8], undefined, true);
    addBox(yard, cabinB, [3.4, 2.35, 2.2], [15.5, 1.28, -11], undefined, true);
    addBox(yard, fenceMat, [0.5, 0.35, 0.7], [-14.5, 2.75, -8]);

    [-8.2, -7.6, -7.0].forEach((z, i) => {
      addCyl(yard, rebarMat, 0.045, 4.2, [-8.2, 0.2 + i * 0.09, z], "x");
    });

    for (let x = -14; x <= 12; x += 3.2) {
      addBox(yard, fenceMat, [0.08, 1.15, 0.08], [x, 0.7, -16]);
    }
    addBox(yard, fenceMat, [26, 0.06, 0.06], [-1, 0.45, -16]);
    addBox(yard, fenceMat, [26, 0.06, 0.06], [-1, 1.05, -16]);

    addCyl(yard, fenceMat, 0.06, 8, [-13, 4, 6], "y");

    const grass = new THREE.MeshStandardMaterial({ color: "#1a3328", roughness: 0.95, metalness: 0 });
    const walk = new THREE.MeshStandardMaterial({ color: "#4a463f", roughness: 0.72, metalness: 0.04 });
    const road = new THREE.MeshStandardMaterial({ color: "#23282e", roughness: 0.84, metalness: 0.08 });
    const canopyMat = new THREE.MeshStandardMaterial({ color: "#1c4632", roughness: 0.82, metalness: 0 });
    const trunkMat = new THREE.MeshStandardMaterial({ color: "#3a3128", roughness: 0.86, metalness: 0 });
    const lampMat = new THREE.MeshStandardMaterial({
      color: "#fff1d2",
      emissive: "#ffd7a1",
      emissiveIntensity: 2.2,
      roughness: 0.3,
    });
    const glassCar = new THREE.MeshStandardMaterial({
      color: "#9eb4c4",
      roughness: 0.08,
      metalness: 0.6,
      envMapIntensity: 1.2,
    });
    const carColors = ["#1c2833", "#8c3d32", "#d8d2c8"].map(
      (color) => new THREE.MeshStandardMaterial({ color, roughness: 0.35, metalness: 0.45, envMapIntensity: 0.8 }),
    );
    const cityMat = new THREE.MeshStandardMaterial({ color: "#141a22", roughness: 0.8, metalness: 0.1 });
    const windowMat = new THREE.MeshStandardMaterial({
      color: "#ffd2a2",
      emissive: "#ffb56a",
      emissiveIntensity: 1.3,
      roughness: 0.4,
    });

    addBox(yard, grass, [22, 0.08, 12], [-24, 0.05, 10]);
    addBox(yard, grass, [18, 0.08, 14], [24, 0.05, 8]);
    addBox(yard, grass, [36, 0.08, 7], [0, 0.05, 18]);
    addBox(yard, walk, [3.2, 0.07, 12], [0.4, 0.07, 13]);
    addBox(yard, road, [78, 0.05, 7], [0, 0.04, 26]);
    addBox(yard, walk, [78, 0.04, 0.12], [0, 0.08, 22.7]);

    function treeAt(x: number, z: number, scale = 1) {
      addCyl(yard, trunkMat, 0.12 * scale, 1.8 * scale, [x, 0.9 * scale, z], "y");
      addSphere(yard, canopyMat, 0.85 * scale, [x, 2.15 * scale, z]);
      addSphere(yard, canopyMat, 0.55 * scale, [x + 0.35 * scale, 1.85 * scale, z + 0.2]);
    }
    [
      [-16, 15, 1.15],
      [-11, 17, 0.85],
      [12, 16, 1.05],
      [17, 14, 0.9],
      [-20, 6, 1.25],
      [20, 4, 1.1],
      [-8, 20, 0.75],
      [7, 19, 0.8],
    ].forEach(([x, z, scale]) => treeAt(x, z, scale));

    function carAt(x: number, z: number, color: THREE.Material, yaw: number) {
      const body = new THREE.Group();
      body.position.set(x, 0.28, z);
      body.rotation.y = yaw;
      yard.add(body);
      addBox(body, color, [1.9, 0.42, 0.82], [0, 0.16, 0]);
      addBox(body, glassCar, [0.95, 0.32, 0.74], [-0.05, 0.48, 0]);
      addCyl(body, trim, 0.16, 0.12, [-0.62, 0.02, 0.38], "x");
      addCyl(body, trim, 0.16, 0.12, [0.62, 0.02, 0.38], "x");
      addCyl(body, trim, 0.16, 0.12, [-0.62, 0.02, -0.38], "x");
      addCyl(body, trim, 0.16, 0.12, [0.62, 0.02, -0.38], "x");
    }
    carAt(-8, 26, carColors[0], 0.15);
    carAt(3.5, 26.4, carColors[1], -0.05);
    carAt(14, 25.6, carColors[2], 0.08);

    [[-3.2, 12.5], [4.2, 12.5], [-6.5, 19], [8, 18.5]].forEach(([x, z]) => {
      addCyl(yard, trim, 0.05, 3.1, [x, 1.55, z], "y");
      addBox(yard, lampMat, [0.42, 0.06, 0.16], [x, 3.12, z]);
    });

    [
      [-30, 5.5, -24],
      [-20, 9, -30],
      [18, 6.5, -28],
      [28, 4, -22],
      [-12, 3.2, -26],
    ].forEach(([x, h, z]) => {
      addBox(yard, cityMat, [4.2, h, 3.4], [x, h / 2, z]);
      for (let wy = 1.2; wy < h - 0.6; wy += 1.1) {
        addBox(yard, windowMat, [2.4, 0.12, 0.06], [x, wy, z + 1.72]);
      }
    });

    compact(concrete);
    compact(interior);
    compact(yard);

    // Facade sits just outside the slab box (x −9…9, z −7…7). Side walls own the corners.
    type Wall = { length: number; ax: number; az: number; ox: number; oz: number; cx: number; cz: number };
    const walls: Wall[] = [
      { length: 17.96, ax: 1, az: 0, ox: 0, oz: 1, cx: 0, cz: 7.1 },
      { length: 17.96, ax: -1, az: 0, ox: 0, oz: -1, cx: 0, cz: -7.1 },
      { length: 14.24, ax: 0, az: -1, ox: 1, oz: 0, cx: 9.1, cz: 0 },
      { length: 14.24, ax: 0, az: 1, ox: -1, oz: 0, cx: -9.1, cz: 0 },
    ];
    const stories = [
      { floor: 1, y0: 0.45, y1: 3.44 },
      { floor: 2, y0: 3.44, y1: 6.59 },
      { floor: 3, y0: 6.59, y1: 9.74 },
      { floor: 4, y0: 9.74, y1: 12.89 },
      { floor: 5, y0: 12.89, y1: 16.12 },
    ];
    const facadeFloors: {
      group: THREE.Group;
      floor: number;
      baseY: number;
      stone: THREE.MeshStandardMaterial;
      glass: THREE.MeshStandardMaterial;
      metal: THREE.MeshStandardMaterial;
      plinth: THREE.MeshStandardMaterial | null;
      solid: boolean;
    }[] = [];

    function putBox(
      geos: THREE.BufferGeometry[],
      wall: Wall,
      along: number,
      yCenter: number,
      span: number,
      height: number,
      thick: number,
      out: number,
    ) {
      const alongX = Math.abs(wall.ax) > 0.5;
      const raw = new THREE.BoxGeometry(alongX ? span : thick, height, alongX ? thick : span);
      raw.translate(
        wall.cx + wall.ax * along + wall.ox * out,
        yCenter,
        wall.cz + wall.az * along + wall.oz * out,
      );
      const geo = raw.toNonIndexed();
      raw.dispose();
      geos.push(geo);
    }

    stories.forEach((story) => {
      const H = story.y1 - story.y0;
      const stoneG: THREE.BufferGeometry[] = [];
      const glassG: THREE.BufferGeometry[] = [];
      const metalG: THREE.BufferGeometry[] = [];
      const plinthG: THREE.BufferGeometry[] = [];
      const spandrel = story.floor === 1 ? 0.38 : 0.18;
      walls.forEach((wall, face) => {
        const count = Math.max(5, Math.round(wall.length / 1.75));
        const pitch = wall.length / count;
        const winW = pitch * 0.64;
        for (let i = 0; i < count; i++) {
          const along = -wall.length / 2 + pitch * (i + 0.5);
          const lobby = story.floor === 1 && face === 0 && Math.abs(along) < pitch * 1.6;
          const sillH = lobby ? 0.18 : spandrel;
          const headH = 0.07;
          const glassH = H - sillH - headH;
          putBox(stoneG, wall, along, sillH / 2, pitch - 0.045, sillH, 0.2, 0);
          putBox(stoneG, wall, along, H - headH / 2, pitch - 0.045, headH, 0.2, 0);
          putBox(glassG, wall, along, sillH + glassH / 2, winW, glassH, 0.04, -0.05);
          const jambH = H - sillH;
          const jambY = sillH + jambH / 2;
          putBox(metalG, wall, along - winW / 2, jambY, 0.05, jambH, 0.11, 0.03);
          putBox(metalG, wall, along + winW / 2, jambY, 0.05, jambH, 0.11, 0.03);
          putBox(metalG, wall, along, sillH + glassH * 0.46, winW, 0.045, 0.09, 0.025);
        }
      });
      if (story.floor === 1) {
        const skirtH = 0.46;
        const skirts = [
          new THREE.BoxGeometry(18.36, skirtH, 0.28),
          new THREE.BoxGeometry(18.36, skirtH, 0.28),
          new THREE.BoxGeometry(0.28, skirtH, 14.36),
          new THREE.BoxGeometry(0.28, skirtH, 14.36),
        ];
        skirts[0].translate(0, -skirtH / 2, 7.16);
        skirts[1].translate(0, -skirtH / 2, -7.16);
        skirts[2].translate(9.16, -skirtH / 2, 0);
        skirts[3].translate(-9.16, -skirtH / 2, 0);
        skirts.forEach((raw) => {
          const geo = raw.toNonIndexed();
          raw.dispose();
          plinthG.push(geo);
        });
      }
      if (story.floor === 5) {
        const parapetH = 0.72;
        const parapet = [
          new THREE.BoxGeometry(18.16, parapetH, 0.18),
          new THREE.BoxGeometry(18.16, parapetH, 0.18),
          new THREE.BoxGeometry(0.18, parapetH, 14.2),
          new THREE.BoxGeometry(0.18, parapetH, 14.2),
        ];
        parapet[0].translate(0, H + parapetH / 2, 7.1);
        parapet[1].translate(0, H + parapetH / 2, -7.1);
        parapet[2].translate(9.1, H + parapetH / 2, 0);
        parapet[3].translate(-9.1, H + parapetH / 2, 0);
        parapet.forEach((raw) => {
          const geo = raw.toNonIndexed();
          raw.dispose();
          stoneG.push(geo);
        });
        const copeY = H + parapetH + 0.045;
        const copes = [
          new THREE.BoxGeometry(18.48, 0.08, 0.32),
          new THREE.BoxGeometry(18.48, 0.08, 0.32),
          new THREE.BoxGeometry(0.32, 0.08, 14.52),
          new THREE.BoxGeometry(0.32, 0.08, 14.52),
        ];
        copes[0].translate(0, copeY, 7.1);
        copes[1].translate(0, copeY, -7.1);
        copes[2].translate(9.1, copeY, 0);
        copes[3].translate(-9.1, copeY, 0);
        copes.forEach((raw) => {
          const geo = raw.toNonIndexed();
          raw.dispose();
          metalG.push(geo);
        });
        const roof = new THREE.BoxGeometry(17.9, 0.1, 13.9);
        roof.translate(0, H + 0.05, 0);
        const roofGeo = roof.toNonIndexed();
        roof.dispose();
        stoneG.push(roofGeo);
      }

      const stone = new THREE.MeshStandardMaterial({
        color: "#efeae3",
        roughness: 0.38,
        metalness: 0.02,
        envMapIntensity: 0.25,
        transparent: true,
        opacity: 0,
        depthWrite: false,
      });
      const glass = new THREE.MeshStandardMaterial({
        color: "#b7c9d6",
        roughness: 0.06,
        metalness: 0.22,
        emissive: "#ffc49a",
        emissiveIntensity: 0.05,
        envMapIntensity: 1.15,
        transparent: true,
        opacity: 0.2,
        depthWrite: false,
      });
      const metal = new THREE.MeshStandardMaterial({
        color: "#1c2228",
        roughness: 0.22,
        metalness: 0.84,
        envMapIntensity: 1.4,
        transparent: true,
        opacity: 0,
        depthWrite: false,
      });
      const group = new THREE.Group();
      group.position.y = story.y0;
      group.visible = false;
      const stoneMesh = new THREE.Mesh(mergeGeos(stoneG), stone);
      stoneMesh.castShadow = true;
      stoneMesh.receiveShadow = true;
      group.add(stoneMesh);
      group.add(new THREE.Mesh(mergeGeos(glassG), glass));
      group.add(new THREE.Mesh(mergeGeos(metalG), metal));
      let plinth: THREE.MeshStandardMaterial | null = null;
      if (plinthG.length) {
        plinth = new THREE.MeshStandardMaterial({
          color: "#3a342f",
          roughness: 0.86,
          metalness: 0.04,
          transparent: true,
          opacity: 0,
          depthWrite: false,
        });
        const plinthMesh = new THREE.Mesh(mergeGeos(plinthG), plinth);
        plinthMesh.castShadow = true;
        group.add(plinthMesh);
      }
      scene.add(group);
      facadeFloors.push({ group, floor: story.floor, baseY: story.y0, stone, glass, metal, plinth, solid: false });
    });

    const slabY: Record<number, number> = { [-1]: 0.55, 1: 3.46, 2: 6.61, 3: 9.76, 4: 12.91, 5: 16.06 };

    let mode: ViewMode = "section";
    let shownFloor = 5;
    let scrollAmt = reduced ? 1 : 0;
    let ringBase = 0.32;
    let ringEm = 0.16;
    let onScreen = true;
    let park: "fixed" | "bottom" = "bottom";
    const facadeDir = new THREE.Vector3(0.28, 0.1, 1).normalize();
    const facadePos = new THREE.Vector3();
    const facadeTarget = new THREE.Vector3(0, 7.5, 0);
    const viewPos = new THREE.Vector3();
    const viewTarget = new THREE.Vector3();
    const fog = scene.fog as THREE.FogExp2;
    const io = new IntersectionObserver(([entry]) => {
      onScreen = entry.isIntersecting;
    });
    io.observe(trackRef.current ?? stage);

    function applyFloor(maxFloor: number) {
      shownFloor = maxFloor;
      tracked.forEach((mesh) => {
        if (mesh.parent === skin) return;
        const tag = mesh.userData.floor;
        if (typeof tag === "number") mesh.visible = tag <= maxFloor;
      });
      ring.position.y = slabY[maxFloor] ?? 16.06;
    }

    function applyLayer(next: Layer) {
      rebarDeep.visible = next === "rebar";
      const ghost = next === "rebar";
      concreteMats.forEach((mat) => {
        mat.transparent = ghost;
        mat.opacity = ghost ? 0.2 : 1;
        mat.depthWrite = !ghost;
        mat.emissive.set(next === "estimate" ? "#5c4a2c" : "#000000");
        mat.emissiveIntensity = next === "estimate" ? 0.28 : 0;
        mat.needsUpdate = true;
      });
      mepMats.forEach((mat) => {
        mat.opacity = next === "mep" ? 1 : 0.2;
        mat.emissive.set(next === "mep" ? "#3a2418" : "#000000");
        mat.emissiveIntensity = next === "mep" ? 0.45 : 0;
      });
      ringBase = next === "ks" ? 1 : 0.32;
      ringEm = next === "ks" ? 0.85 : 0.16;
    }

    function applyView(next: ViewMode) {
      mode = next;
    }

    function frameFacade() {
      const aspect = Math.max(camera.aspect, 0.34);
      const vHalf = THREE.MathUtils.degToRad(15);
      const hHalf = Math.atan(Math.tan(vHalf) * aspect);
      const dist = Math.max(10.6 / Math.tan(vHalf), 11.2 / Math.tan(hHalf)) + 5;
      facadePos.copy(facadeTarget).addScaledVector(facadeDir, dist);
    }

    function parkPin(next: "fixed" | "bottom") {
      const pin = pinRef.current;
      if (!pin || park === next) return;
      park = next;
      pin.style.position = next === "fixed" ? "fixed" : "absolute";
      pin.style.left = "0";
      pin.style.width = "100%";
      pin.style.height = "100dvh";
      pin.style.zIndex = "0";
      if (next === "bottom") {
        pin.style.top = "auto";
        pin.style.bottom = "0";
      } else {
        pin.style.top = "0";
        pin.style.bottom = "auto";
      }
    }

    function syncUi(p: number) {
      const ui = uiRef.current;
      if (ui && !reduced) {
        const fade = smoother(0.58, 0.86, p);
        ui.style.opacity = String(1 - fade);
        const off = fade > 0.82;
        if (off) ui.setAttribute("inert", "");
        else ui.removeAttribute("inert");
      }
    }
    syncUiRef.current = syncUi;

    function onScroll() {
      scrollRef.current = scrollAmt;
      if (reduced) {
        scrollAmt = 1;
        scrollRef.current = 1;
        syncUi(1);
        return;
      }
      const track = trackRef.current;
      if (!track) return;
      const rect = track.getBoundingClientRect();
      const vh = window.innerHeight || 1;
      const total = Math.max(rect.height - vh, 1);
      const scrolled = Math.min(Math.max(-rect.top, 0), total);
      scrollAmt = scrolled / total;
      scrollRef.current = scrollAmt;
      parkPin(rect.bottom <= vh + 0.5 ? "bottom" : "fixed");
      syncUi(scrollAmt);
    }

    applyFloor(5);
    applyLayer("concrete");
    applyView("section");

    function resize() {
      const w = stage.clientWidth || 1;
      const h = stage.clientHeight || 1;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      const dpr = Math.min(window.devicePixelRatio || 1, w < 900 ? 1 : 1.25);
      renderer.setPixelRatio(dpr);
      renderer.setSize(w, h, false);
    }
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(stage);

    const timer = new THREE.Timer();
    timer.connect(document);
    const loop = (now: number) => {
      if (cancelled) return;
      raf = requestAnimationFrame(loop);
      if (!onScreen || document.hidden) return;
      timer.update(now);
      const t = timer.getElapsed();
      const p = scrollAmt;

      facadeFloors.forEach((item) => {
        const show = item.floor <= shownFloor;
        item.group.visible = show;
        if (!show) return;
        item.group.position.y = item.baseY;
        if (!item.solid) {
          item.solid = true;
          item.stone.transparent = false;
          item.metal.transparent = false;
          item.stone.opacity = 1;
          item.metal.opacity = 1;
          item.stone.depthWrite = true;
          item.metal.depthWrite = true;
          item.glass.transparent = true;
          item.glass.opacity = 0.2;
          item.glass.depthWrite = false;
          if (item.plinth) {
            item.plinth.transparent = false;
            item.plinth.opacity = 1;
            item.plinth.depthWrite = true;
          }
          item.stone.needsUpdate = true;
          item.metal.needsUpdate = true;
          item.glass.needsUpdate = true;
          if (item.plinth) item.plinth.needsUpdate = true;
        }
      });

      for (const child of skin.children) {
        const mesh = child as THREE.Mesh;
        const fl = mesh.userData.floor as number;
        if (typeof fl !== "number") continue;
        const reveal = reduced ? 1 : smoother(0.06 + (fl - 1) * 0.11, 0.2 + (fl - 1) * 0.11, p);
        const opened = mode === "site" && !reduced && p < 0.02;
        mesh.visible = fl <= shownFloor && (opened || reveal > 0.12);
      }

      works.visible = false;
      rebarHero.visible = false;
      yard.visible = mode === "site" || p < 0.16;
      const ringK = reduced ? 0 : 1 - smoother(0.24, 0.52, p);
      ring.visible = ringK > 0.03;
      ringMat.opacity = ringBase * ringK;
      ringMat.emissiveIntensity = ringEm * ringK;

      const preset = VIEWS[mode];
      const tone = HEALTH_HEX[driveRef.current.health];
      ringMat.color.setHex(tone);
      ringMat.emissive.setHex(tone);
      const spin = reduced ? 0 : t * 0.11 * (1 - smoother(0.04, 0.32, p));
      const cs = Math.cos(spin);
      const sn = Math.sin(spin);
      viewPos.set(preset.pos[0] * cs - preset.pos[2] * sn, preset.pos[1], preset.pos[0] * sn + preset.pos[2] * cs);
      viewTarget.set(preset.target[0], preset.target[1], preset.target[2]);
      frameFacade();
      const blend = reduced ? (mode === "section" ? 1 : 0) : smoother(0.02, 0.68, p);
      desiredPos.lerpVectors(viewPos, facadePos, blend);
      desiredTarget.lerpVectors(viewTarget, facadeTarget, blend);
      camPos.lerp(desiredPos, reduced ? 1 : 0.06);
      camTarget.lerp(desiredTarget, reduced ? 1 : 0.06);
      camera.position.copy(camPos);
      camera.lookAt(camTarget);
      fog.density = 0.5 / Math.max(camera.position.distanceTo(camTarget), 8);
      if (!reduced) hook.position.y = 18.4 + Math.sin(t * 0.7) * 0.45;
      renderer.render(scene, camera);
      if (!readyFlag) {
        readyFlag = true;
        if (!cancelled) setReady(true);
      }
    };
    let readyFlag = false;
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    loop(performance.now());

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      syncUiRef.current = () => {};
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      io.disconnect();
      ro.disconnect();
      shadowTex.dispose();
      padTex.dispose();
      grit.dispose();
      envMap.dispose();
      const mats = new Set<THREE.Material>();
      scene.traverse((obj) => {
        const mesh = obj as THREE.Mesh;
        if (mesh.geometry) mesh.geometry.dispose();
        const material = mesh.material;
        if (Array.isArray(material)) material.forEach((m) => mats.add(m));
        else if (material) mats.add(material);
      });
      mats.forEach((m) => m.dispose());
      const bg = scene.background;
      if (bg instanceof THREE.Texture) bg.dispose();
      renderer.dispose();
      if (renderer.domElement.parentElement === stage) stage.removeChild(renderer.domElement);
    };
  }, []);

  return (
    <section
      ref={trackRef}
      className="relative ml-[calc(50%-50vw)] mr-[calc(50%-50vw)] w-screen bg-[#101726]"
      style={{ height: reducedMotion ? "100dvh" : "250vh" }}
    >
      <div ref={pinRef} className="absolute left-0 top-0 z-0 h-[100dvh] w-full overflow-hidden bg-[#101726]">
        <div ref={hostRef} className="absolute inset-0" role="img" aria-label={t.canvas} />
        <div ref={uiRef} className="pointer-events-none absolute inset-0 z-10">
          <aside className="pointer-events-auto absolute inset-x-3 bottom-[4.75rem] top-auto h-[42dvh] overflow-hidden rounded-[22px] border border-white/10 bg-[rgba(8,14,24,0.9)] shadow-[0_24px_60px_-28px_rgba(0,0,0,0.85)] lg:inset-x-auto lg:bottom-8 lg:left-8 lg:top-24 lg:h-auto lg:w-[360px]">
            <div className="flex h-full flex-col">
              <div className="flex items-center justify-between gap-3 px-4 pb-3 pt-4">
                <div>
                  <p className="flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-white/45">
                    <span className="relative flex h-1.5 w-1.5">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#7dcea0] opacity-70 motion-reduce:animate-none" />
                      <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#7dcea0]" />
                    </span>
                    {t.kicker}
                  </p>
                  <h1 className="mt-1 text-[22px] font-semibold leading-none tracking-tight text-white">{t.live}</h1>
                </div>
                <p className="text-right font-mono text-[11px] text-white/45">
                  {snaps.length > 0 ? `${snaps.length} ${t.sites}` : ""}
                  <span className="mt-1 block">{updated ? `${t.updated} ${clock(updated)}` : "—"}</span>
                </p>
              </div>
              <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto px-2 pb-2 [scrollbar-width:thin]">
                {snaps.length === 0 ? (
                  <p className="px-2 py-6 text-[13px] text-white/55">
                    {loadState === "error" ? t.failed : loadState === "loading" ? t.waiting : t.empty}
                  </p>
                ) : (
                  snaps.map((row) => {
                    const on = row.project.id === active?.project.id;
                    const pct = row.budget_kzt > 0 ? Math.min(100, Math.round((row.actual_kzt / row.budget_kzt) * 100)) : 0;
                    const tone = row.health === "red" ? "bg-[#e07a68]" : row.health === "amber" ? "bg-[#e2b657]" : "bg-[#7dcea0]";
                    return (
                      <button
                        key={row.project.id}
                        type="button"
                        onClick={() => setSelected(row.project.id)}
                        className={`w-full rounded-2xl px-3 py-2.5 text-left transition-colors ${
                          on ? "bg-white/10" : "hover:bg-white/5"
                        }`}
                      >
                        <span className="flex items-start gap-2.5">
                          <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${tone}`} />
                          <span className="min-w-0">
                            <span className="block truncate text-[14px] font-semibold text-white">{row.project.title}</span>
                            <span className="mt-0.5 block truncate text-[12px] text-white/50">{row.project.address}</span>
                          </span>
                          <span className="ml-auto shrink-0 font-mono text-[12px] text-white/70">{pct}%</span>
                        </span>
                      </button>
                    );
                  })
                )}
              </div>
              {active ? (
                <div className="border-t border-white/10 px-4 py-3.5">
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="truncate text-[13px] font-medium text-white/80">{active.project.title}</p>
                    <p className="font-mono text-[12px] text-white">
                      {active.budget_kzt > 0 ? `${Math.min(100, Math.round((active.actual_kzt / active.budget_kzt) * 100))}%` : "0%"}
                    </p>
                  </div>
                  <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/10">
                    <div
                      className={`h-full rounded-full ${
                        active.health === "red" ? "bg-[#e07a68]" : active.health === "amber" ? "bg-[#e2b657]" : "bg-[#7dcea0]"
                      }`}
                      style={{
                        width: `${active.budget_kzt > 0 ? Math.min(100, Math.round((active.actual_kzt / active.budget_kzt) * 100)) : 0}%`,
                      }}
                    />
                  </div>
                  <dl className="mt-3 grid grid-cols-3 gap-2">
                    {[
                      [t.budget, tenge(active.budget_kzt)],
                      [t.actual, tenge(active.actual_kzt)],
                      [t.committed, tenge(active.committed_kzt)],
                      [t.rfi, String(active.open_rfi)],
                      [t.punch, String(active.open_punch)],
                      [t.drawings, String(active.counts.drawings)],
                    ].map(([label, value]) => (
                      <div key={label}>
                        <dt className="text-[10px] uppercase tracking-[0.12em] text-white/35">{label}</dt>
                        <dd className="mt-0.5 font-mono text-[12px] text-white">{value}</dd>
                      </div>
                    ))}
                  </dl>
                  <Link
                    href={`/${locale}/site/${active.project.id}`}
                    className="mt-3.5 flex h-11 items-center justify-center rounded-full bg-[#2F5B8A] text-[13px] font-semibold text-white transition-colors hover:bg-[#3a6c9e] active:scale-[0.98]"
                  >
                    {t.open}
                  </Link>
                </div>
              ) : null}
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}
