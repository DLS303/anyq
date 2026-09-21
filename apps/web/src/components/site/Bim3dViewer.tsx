"use client";

import React, { useEffect, useRef, useState, useMemo } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Locale } from "@/lib/types";
import dynamic from "next/dynamic";

const PdfDrawingViewer = dynamic(
  () => import("./PdfDrawingViewer").then((m) => m.PdfDrawingViewer),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center p-12 text-ink/50 glass rounded-2xl">
        <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-pine mr-3" />
        Загрузка PDF CAD чертежа...
      </div>
    ),
  }
);

interface DrawingItem {
  id: string;
  code: string;
  title: string;
  revision: string;
  current: boolean;
  file?: string;
}

interface Props {
  locale: Locale;
  drawings: DrawingItem[];
  projectId: string;
  projectTitle?: string;
}

type RenderMode = "realistic" | "wireframe" | "xray" | "blueprint";
type ViewPreset = "iso" | "top" | "front" | "side";
type ActiveTab = "3d" | "2d";

export function Bim3dViewer({ locale, drawings, projectId, projectTitle = "Коттедж 180 м²" }: Props) {
  const isKk = locale === "kk";
  const containerRef = useRef<HTMLDivElement>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("3d");
  const [selectedDrawing, setSelectedDrawing] = useState<DrawingItem | null>(drawings[0] || null);

  // Layer visibility toggles
  const [showArch, setShowArch] = useState(true);
  const [showConcrete, setShowConcrete] = useState(true);
  const [showRoof, setShowRoof] = useState(true);
  const [showMep, setShowMep] = useState(true);
  const [showRebar, setShowRebar] = useState(false);
  const [showMarkers, setShowMarkers] = useState(true);

  // Render & Camera controls
  const [renderMode, setRenderMode] = useState<RenderMode>("realistic");
  const [clipHeight, setClipHeight] = useState<number>(9.0); // 0 to 9m
  const [activeMarker, setActiveMarker] = useState<string | null>(null);
  const [rulerActive, setRulerActive] = useState(false);
  const [rulerPoints, setRulerPoints] = useState<THREE.Vector3[]>([]);
  const [rulerDistance, setRulerDistance] = useState<number | null>(null);

  // Three.js refs
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const clipPlaneRef = useRef<THREE.Plane | null>(null);

  // Groups
  const groupArchRef = useRef<THREE.Group | null>(null);
  const groupConcreteRef = useRef<THREE.Group | null>(null);
  const groupRoofRef = useRef<THREE.Group | null>(null);
  const groupMepRef = useRef<THREE.Group | null>(null);
  const groupRebarRef = useRef<THREE.Group | null>(null);
  const groupMarkersRef = useRef<THREE.Group | null>(null);

  // Materials map for quick mode switching
  const materialsRef = useRef<THREE.Material[]>([]);

  // Initialize Three.js Scene
  useEffect(() => {
    if (!containerRef.current || activeTab !== "3d") return;
    const container = containerRef.current;
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 560;

    // 1. Scene
    const scene = new THREE.Scene();
    sceneRef.current = scene;
    scene.background = new THREE.Color(0xF4F6F9);

    // Fog for depth
    scene.fog = new THREE.FogExp2(0xF4F6F9, 0.015);

    // 2. Camera
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 200);
    camera.position.set(18, 14, 22);
    cameraRef.current = camera;

    // 3. Clipping plane for vertical section cut
    const clipPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 9.0);
    clipPlaneRef.current = clipPlane;

    // 4. Renderer
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.localClippingEnabled = true;
    rendererRef.current = renderer;
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    // 5. OrbitControls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxPolarAngle = Math.PI / 2 - 0.02; // Don't go below ground
    controls.minDistance = 4;
    controls.maxDistance = 60;
    controls.target.set(0, 3.5, 0);
    controlsRef.current = controls;

    // 6. Lighting
    const hemiLight = new THREE.HemisphereLight(0xffffff, 0x556677, 0.7);
    scene.add(hemiLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
    dirLight.position.set(20, 30, 15);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 1024;
    dirLight.shadow.mapSize.height = 1024;
    dirLight.shadow.camera.near = 1;
    dirLight.shadow.camera.far = 80;
    dirLight.shadow.camera.left = -20;
    dirLight.shadow.camera.right = 20;
    dirLight.shadow.camera.top = 20;
    dirLight.shadow.camera.bottom = -20;
    scene.add(dirLight);

    const fillLight = new THREE.DirectionalLight(0xbad7f5, 0.4);
    fillLight.position.set(-15, 10, -15);
    scene.add(fillLight);

    // 7. Ground Grid & Site
    const grid = new THREE.GridHelper(40, 40, 0x2E75B6, 0xD0D7DE);
    grid.position.y = -0.01;
    scene.add(grid);

    // Ground grass patch
    const groundGeo = new THREE.PlaneGeometry(36, 36);
    const groundMat = new THREE.MeshStandardMaterial({
      color: 0x8FA876,
      roughness: 0.9,
      metalness: 0.1,
    });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.02;
    ground.receiveShadow = true;
    scene.add(ground);

    // 8. Build Procedural BIM Building
    const mats: THREE.Material[] = [];
    const registerMat = <T extends THREE.Material>(m: T): T => {
      m.clippingPlanes = [clipPlane];
      m.clipShadows = true;
      mats.push(m);
      return m;
    };

    // Material definitions
    const concreteMat = registerMat(
      new THREE.MeshStandardMaterial({ color: 0x8A9096, roughness: 0.85, metalness: 0.15 })
    );
    const wallPlasterMat = registerMat(
      new THREE.MeshStandardMaterial({ color: 0xEDE8DF, roughness: 0.7, metalness: 0.05 })
    );
    const timberFacadeMat = registerMat(
      new THREE.MeshStandardMaterial({ color: 0x543A26, roughness: 0.6, metalness: 0.1 })
    );
    const glassMat = registerMat(
      new THREE.MeshPhysicalMaterial({
        color: 0x90C2E7,
        transparent: true,
        opacity: 0.45,
        roughness: 0.1,
        transmission: 0.85,
        ior: 1.5,
      })
    );
    const windowFrameMat = registerMat(
      new THREE.MeshStandardMaterial({ color: 0x24282D, roughness: 0.4, metalness: 0.8 })
    );
    const roofMat = registerMat(
      new THREE.MeshStandardMaterial({ color: 0x1E242B, roughness: 0.45, metalness: 0.55 })
    );
    const trussWoodMat = registerMat(
      new THREE.MeshStandardMaterial({ color: 0xC99F68, roughness: 0.8, metalness: 0.1 })
    );
    const rebarMat = registerMat(
      new THREE.MeshStandardMaterial({ color: 0x47515E, roughness: 0.3, metalness: 0.9 })
    );
    const hotPipeMat = registerMat(
      new THREE.MeshStandardMaterial({ color: 0xD32F2F, roughness: 0.3, metalness: 0.5 })
    );
    const coldPipeMat = registerMat(
      new THREE.MeshStandardMaterial({ color: 0x1976D2, roughness: 0.3, metalness: 0.5 })
    );
    const sewerPipeMat = registerMat(
      new THREE.MeshStandardMaterial({ color: 0xE65100, roughness: 0.4, metalness: 0.2 })
    );
    const ventDuctMat = registerMat(
      new THREE.MeshStandardMaterial({ color: 0xB0BEC5, roughness: 0.2, metalness: 0.85 })
    );
    materialsRef.current = mats;

    // --- Group: Concrete & Foundation (КЖ) ---
    const groupConcrete = new THREE.Group();
    groupConcreteRef.current = groupConcrete;
    scene.add(groupConcrete);

    // Foundation Slab (12.4 x 9.8 x 0.35m)
    const slabGeo = new THREE.BoxGeometry(12.4, 0.35, 9.8);
    const fndSlab = new THREE.Mesh(slabGeo, concreteMat);
    fndSlab.position.set(0, 0.175, 0);
    fndSlab.castShadow = true;
    fndSlab.receiveShadow = true;
    groupConcrete.add(fndSlab);

    // Concrete Blind Area (Отмостка)
    const otmGeo = new THREE.BoxGeometry(14.0, 0.1, 11.4);
    const otmMesh = new THREE.Mesh(otmGeo, concreteMat);
    otmMesh.position.set(0, 0.05, 0);
    otmMesh.receiveShadow = true;
    groupConcrete.add(otmMesh);

    // Interfloor Slab (1st -> 2nd floor, 12.0 x 9.4 x 0.22m)
    const interSlabGeo = new THREE.BoxGeometry(12.0, 0.22, 9.4);
    const interSlab = new THREE.Mesh(interSlabGeo, concreteMat);
    interSlab.position.set(0, 3.46, 0);
    interSlab.castShadow = true;
    interSlab.receiveShadow = true;
    groupConcrete.add(interSlab);

    // Reinforced concrete columns (4 corners + 2 center)
    const colGeo = new THREE.BoxGeometry(0.35, 3.1, 0.35);
    const colCoords = [
      [-5.8, 1.9, -4.5], [5.8, 1.9, -4.5],
      [-5.8, 1.9, 4.5], [5.8, 1.9, 4.5],
      [0, 1.9, 0], [0, 5.1, 0],
    ];
    colCoords.forEach(([cx, cy, cz]) => {
      const col = new THREE.Mesh(colGeo, concreteMat);
      col.position.set(cx, cy, cz);
      col.castShadow = true;
      groupConcrete.add(col);
    });

    // --- Group: Rebar Cage (Арматурный каркас А500С) ---
    const groupRebar = new THREE.Group();
    groupRebarRef.current = groupRebar;
    groupRebar.visible = false;
    scene.add(groupRebar);

    // Rebar grid lines in slab
    for (let rx = -5.8; rx <= 5.8; rx += 0.8) {
      const barGeo = new THREE.CylinderGeometry(0.012, 0.012, 9.4, 6);
      const bar = new THREE.Mesh(barGeo, rebarMat);
      bar.rotation.x = Math.PI / 2;
      bar.position.set(rx, 0.2, 0);
      groupRebar.add(bar);
    }
    for (let rz = -4.5; rz <= 4.5; rz += 0.8) {
      const barGeo = new THREE.CylinderGeometry(0.012, 0.012, 11.8, 6);
      const bar = new THREE.Mesh(barGeo, rebarMat);
      bar.rotation.z = Math.PI / 2;
      bar.position.set(0, 0.22, rz);
      groupRebar.add(bar);
    }

    // --- Group: Architecture Floor 1 & 2 (АР) ---
    const groupArch = new THREE.Group();
    groupArchRef.current = groupArch;
    scene.add(groupArch);

    // Ground floor exterior walls
    // Front wall with door & window cutouts
    const wallF1Geo = new THREE.BoxGeometry(12.0, 3.1, 0.38);
    const wallBack = new THREE.Mesh(wallF1Geo, wallPlasterMat);
    wallBack.position.set(0, 1.9, -4.6);
    wallBack.castShadow = true;
    groupArch.add(wallBack);

    // Left & right walls
    const wallSideGeo = new THREE.BoxGeometry(0.38, 3.1, 9.2);
    const wallLeft = new THREE.Mesh(wallSideGeo, wallPlasterMat);
    wallLeft.position.set(-5.9, 1.9, 0);
    wallLeft.castShadow = true;
    groupArch.add(wallLeft);

    const wallRight = new THREE.Mesh(wallSideGeo, timberFacadeMat);
    wallRight.position.set(5.9, 1.9, 0);
    wallRight.castShadow = true;
    groupArch.add(wallRight);

    // Front wall sections (with entrance and panoramic window)
    const frontL = new THREE.Mesh(new THREE.BoxGeometry(3.5, 3.1, 0.38), timberFacadeMat);
    frontL.position.set(-4.2, 1.9, 4.6);
    frontL.castShadow = true;
    groupArch.add(frontL);

    const frontR = new THREE.Mesh(new THREE.BoxGeometry(3.5, 3.1, 0.38), wallPlasterMat);
    frontR.position.set(4.2, 1.9, 4.6);
    frontR.castShadow = true;
    groupArch.add(frontR);

    // Panoramic glass window (center)
    const panoGlass = new THREE.Mesh(new THREE.BoxGeometry(4.8, 2.7, 0.05), glassMat);
    panoGlass.position.set(0, 1.9, 4.6);
    groupArch.add(panoGlass);

    // Window frame
    const winFrame = new THREE.Mesh(new THREE.BoxGeometry(5.0, 2.8, 0.12), windowFrameMat);
    winFrame.position.set(0, 1.9, 4.6);
    groupArch.add(winFrame);

    // Front terrace & deck
    const terraceGeo = new THREE.BoxGeometry(6.0, 0.15, 3.0);
    const terrace = new THREE.Mesh(terraceGeo, timberFacadeMat);
    terrace.position.set(0, 0.15, 6.2);
    terrace.receiveShadow = true;
    groupArch.add(terrace);

    // Second Floor Walls (Height: 3.57 to 6.4m)
    const wallF2Geo = new THREE.BoxGeometry(11.8, 2.8, 0.38);
    const wall2Back = new THREE.Mesh(wallF2Geo, wallPlasterMat);
    wall2Back.position.set(0, 4.97, -4.5);
    wall2Back.castShadow = true;
    groupArch.add(wall2Back);

    const wall2Front = new THREE.Mesh(new THREE.BoxGeometry(11.8, 2.8, 0.38), timberFacadeMat);
    wall2Front.position.set(0, 4.97, 4.5);
    wall2Front.castShadow = true;
    groupArch.add(wall2Front);

    const wall2Left = new THREE.Mesh(new THREE.BoxGeometry(0.38, 2.8, 8.8), wallPlasterMat);
    wall2Left.position.set(-5.8, 4.97, 0);
    wall2Left.castShadow = true;
    groupArch.add(wall2Left);

    const wall2Right = new THREE.Mesh(new THREE.BoxGeometry(0.38, 2.8, 8.8), timberFacadeMat);
    wall2Right.position.set(5.8, 4.97, 0);
    wall2Right.castShadow = true;
    groupArch.add(wall2Right);

    // 2nd floor windows
    const f2Windows = [-3.0, 0, 3.0];
    f2Windows.forEach((wx) => {
      const win = new THREE.Mesh(new THREE.BoxGeometry(1.6, 1.8, 0.04), glassMat);
      win.position.set(wx, 5.0, 4.52);
      groupArch.add(win);

      const f = new THREE.Mesh(new THREE.BoxGeometry(1.7, 1.9, 0.1), windowFrameMat);
      f.position.set(wx, 5.0, 4.52);
      groupArch.add(f);
    });

    // Interior partitions 1st floor
    const part1 = new THREE.Mesh(new THREE.BoxGeometry(0.2, 3.1, 5.0), wallPlasterMat);
    part1.position.set(-1.5, 1.9, -1.5);
    groupArch.add(part1);

    const part2 = new THREE.Mesh(new THREE.BoxGeometry(4.0, 3.1, 0.2), wallPlasterMat);
    part2.position.set(-3.5, 1.9, -1.0);
    groupArch.add(part2);

    // Staircase
    for (let s = 0; s < 14; s++) {
      const step = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.18, 0.3), timberFacadeMat);
      step.position.set(4.5, 0.35 + s * 0.22, -3.5 + s * 0.25);
      groupArch.add(step);
    }

    // --- Group: Roof & Trusses (КР) ---
    const groupRoof = new THREE.Group();
    groupRoofRef.current = groupRoof;
    scene.add(groupRoof);

    // Gable Roof Pitch 1 (Left slope)
    const roofSlopeGeo = new THREE.BoxGeometry(12.8, 0.18, 6.2);
    const roofLeft = new THREE.Mesh(roofSlopeGeo, roofMat);
    roofLeft.position.set(0, 7.5, -2.4);
    roofLeft.rotation.x = Math.PI / 6; // 30 degrees
    roofLeft.castShadow = true;
    groupRoof.add(roofLeft);

    // Gable Roof Pitch 2 (Right slope)
    const roofRight = new THREE.Mesh(roofSlopeGeo, roofMat);
    roofRight.position.set(0, 7.5, 2.4);
    roofRight.rotation.x = -Math.PI / 6;
    roofRight.castShadow = true;
    groupRoof.add(roofRight);

    // Gable End Triangles (Фронтоны)
    const gableGeo = new THREE.BufferGeometry();
    const gableVertices = new Float32Array([
      -5.85, 6.37, -4.5,
      -5.85, 6.37, 4.5,
      -5.85, 8.95, 0,
      5.85, 6.37, -4.5,
      5.85, 8.95, 0,
      5.85, 6.37, 4.5,
    ]);
    gableGeo.setAttribute("position", new THREE.BufferAttribute(gableVertices, 3));
    gableGeo.computeVertexNormals();
    const gableMesh = new THREE.Mesh(gableGeo, timberFacadeMat);
    gableMesh.castShadow = true;
    groupRoof.add(gableMesh);

    // Timber Trusses
    for (let tx = -5.0; tx <= 5.0; tx += 2.0) {
      const trussR = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.18, 5.8), trussWoodMat);
      trussR.position.set(tx, 7.4, 2.4);
      trussR.rotation.x = -Math.PI / 6;
      groupRoof.add(trussR);

      const trussL = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.18, 5.8), trussWoodMat);
      trussL.position.set(tx, 7.4, -2.4);
      trussL.rotation.x = Math.PI / 6;
      groupRoof.add(trussL);
    }

    // --- Group: MEP Engineering (ОВ/ВК/ЭОМ) ---
    const groupMep = new THREE.Group();
    groupMepRef.current = groupMep;
    scene.add(groupMep);

    // Underfloor Heating circuits (Red & Blue coils on 1st floor)
    for (let pipeX = -4.5; pipeX <= 4.5; pipeX += 0.5) {
      const isSupply = Math.abs(pipeX * 10) % 10 === 0;
      const pipeGeo = new THREE.CylinderGeometry(0.016, 0.016, 7.5, 8);
      const pipe = new THREE.Mesh(pipeGeo, isSupply ? hotPipeMat : coldPipeMat);
      pipe.rotation.x = Math.PI / 2;
      pipe.position.set(pipeX, 0.37, 0);
      groupMep.add(pipe);
    }

    // Underfloor Heating 2nd floor
    for (let pipeX = -4.0; pipeX <= 4.0; pipeX += 0.6) {
      const pipeGeo = new THREE.CylinderGeometry(0.016, 0.016, 6.5, 8);
      const pipe = new THREE.Mesh(pipeGeo, hotPipeMat);
      pipe.rotation.x = Math.PI / 2;
      pipe.position.set(pipeX, 3.59, 0);
      groupMep.add(pipe);
    }

    // Vertical Sewer Stack (Канализационный стояк Ø110)
    const sewerGeo = new THREE.CylinderGeometry(0.055, 0.055, 8.0, 16);
    const sewer = new THREE.Mesh(sewerGeo, sewerPipeMat);
    sewer.position.set(-2.0, 4.0, -3.0);
    groupMep.add(sewer);

    // Water riser
    const waterRiserGeo = new THREE.CylinderGeometry(0.025, 0.025, 7.5, 12);
    const waterRiser = new THREE.Mesh(waterRiserGeo, coldPipeMat);
    waterRiser.position.set(-2.2, 3.8, -3.0);
    groupMep.add(waterRiser);

    // Ventilation Duct (Оцинкованный короб)
    const ventGeo = new THREE.BoxGeometry(0.3, 7.8, 0.4);
    const vent = new THREE.Mesh(ventGeo, ventDuctMat);
    vent.position.set(-2.5, 3.9, -2.8);
    groupMep.add(vent);

    // Boiler tank in boiler room
    const boilerGeo = new THREE.CylinderGeometry(0.35, 0.35, 1.4, 16);
    const boiler = new THREE.Mesh(boilerGeo, ventDuctMat);
    boiler.position.set(-4.5, 1.05, -3.2);
    groupMep.add(boiler);

    // --- Group: Construction Punch / RFI Pins (Технадзор) ---
    const groupMarkers = new THREE.Group();
    groupMarkersRef.current = groupMarkers;
    scene.add(groupMarkers);

    const markerData = [
      { id: "rfi-1", label: "RFI-001: Отметка цоколя +300", pos: [0, 0.45, 4.7] as [number, number, number], color: 0xF2A93B },
      { id: "sub-1", label: "SUB-012: Газоблок D500", pos: [-5.9, 2.5, 0] as [number, number, number], color: 0x3CB878 },
      { id: "pu-1", label: "PUNCH-01: Дефект ограждения", pos: [6.2, 0.3, 5.0] as [number, number, number], color: 0xE05656 },
      { id: "in-2", label: "INSP-02: Армирование принято", pos: [0, 0.38, -4.5] as [number, number, number], color: 0x2E75B6 },
    ];

    markerData.forEach((m) => {
      const pinGroup = new THREE.Group();
      pinGroup.position.set(...m.pos);

      // Sphere pin head
      const sphereGeo = new THREE.SphereGeometry(0.22, 16, 16);
      const sphereMat = new THREE.MeshStandardMaterial({
        color: m.color,
        emissive: m.color,
        emissiveIntensity: 0.3,
      });
      const sphere = new THREE.Mesh(sphereGeo, sphereMat);
      sphere.position.y = 0.5;
      pinGroup.add(sphere);

      // Pin needle
      const needleGeo = new THREE.CylinderGeometry(0.02, 0.02, 0.5, 8);
      const needleMat = new THREE.MeshStandardMaterial({ color: 0x222222 });
      const needle = new THREE.Mesh(needleGeo, needleMat);
      needle.position.y = 0.25;
      pinGroup.add(needle);

      // User data for raycast
      pinGroup.userData = { markerId: m.id, label: m.label };
      groupMarkers.add(pinGroup);
    });

    // 9. Animation loop
    let reqId = 0;
    const animate = () => {
      reqId = requestAnimationFrame(animate);
      controls.update();

      // Gentle floating pulse for markers
      groupMarkers.children.forEach((p, idx) => {
        p.position.y = markerData[idx].pos[1] + Math.sin(Date.now() * 0.003 + idx) * 0.05;
      });

      renderer.render(scene, camera);
    };
    animate();

    // 10. Resize observer
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width: w, height: h } = entry.contentRect;
        if (w > 0 && h > 0) {
          camera.aspect = w / h;
          camera.updateProjectionMatrix();
          renderer.setSize(w, h);
        }
      }
    });
    resizeObserver.observe(container);

    // Cleanup
    return () => {
      cancelAnimationFrame(reqId);
      resizeObserver.disconnect();
      renderer.dispose();
      controls.dispose();
      materialsRef.current.forEach((m) => m.dispose());
      container.innerHTML = "";
    };
  }, [activeTab]);

  // Sync Layers Visibility
  useEffect(() => {
    if (groupArchRef.current) groupArchRef.current.visible = showArch;
    if (groupConcreteRef.current) groupConcreteRef.current.visible = showConcrete;
    if (groupRoofRef.current) groupRoofRef.current.visible = showRoof;
    if (groupMepRef.current) groupMepRef.current.visible = showMep;
    if (groupRebarRef.current) groupRebarRef.current.visible = showRebar;
    if (groupMarkersRef.current) groupMarkersRef.current.visible = showMarkers;
  }, [showArch, showConcrete, showRoof, showMep, showRebar, showMarkers]);

  // Sync Section Cut (Clipping Plane)
  useEffect(() => {
    if (clipPlaneRef.current) {
      clipPlaneRef.current.constant = clipHeight;
    }
  }, [clipHeight]);

  // Sync Render Modes (Realistic, Wireframe, X-Ray, Blueprint)
  useEffect(() => {
    if (!sceneRef.current) return;
    materialsRef.current.forEach((mat) => {
      if (mat instanceof THREE.MeshStandardMaterial || mat instanceof THREE.MeshPhysicalMaterial) {
        if (renderMode === "wireframe") {
          mat.wireframe = true;
          mat.opacity = 1;
          mat.transparent = false;
        } else if (renderMode === "xray") {
          mat.wireframe = false;
          mat.transparent = true;
          mat.opacity = 0.35;
        } else if (renderMode === "blueprint") {
          mat.wireframe = false;
          mat.transparent = false;
          mat.opacity = 1;
          mat.color.setHex(0x1B365D);
        } else {
          // realistic
          mat.wireframe = false;
          mat.transparent = mat instanceof THREE.MeshPhysicalMaterial;
          mat.opacity = mat instanceof THREE.MeshPhysicalMaterial ? 0.45 : 1;
        }
        mat.needsUpdate = true;
      }
    });

    if (sceneRef.current) {
      sceneRef.current.background = new THREE.Color(
        renderMode === "blueprint" ? 0x0B1E3D : renderMode === "wireframe" ? 0x1E242B : 0xF4F6F9
      );
    }
  }, [renderMode]);

  // Camera Presets
  function setCameraPreset(preset: ViewPreset) {
    const cam = cameraRef.current;
    const ctrl = controlsRef.current;
    if (!cam || !ctrl) return;

    switch (preset) {
      case "iso":
        cam.position.set(18, 14, 22);
        ctrl.target.set(0, 3.5, 0);
        break;
      case "top":
        cam.position.set(0, 30, 0.1);
        ctrl.target.set(0, 0, 0);
        break;
      case "front":
        cam.position.set(0, 4.0, 26);
        ctrl.target.set(0, 3.5, 0);
        break;
      case "side":
        cam.position.set(26, 4.0, 0);
        ctrl.target.set(0, 3.5, 0);
        break;
    }
    ctrl.update();
  }

  // Laser measurement tool on 3D model
  function handleCanvasClick(e: React.MouseEvent<HTMLDivElement>) {
    if (!rulerActive || !containerRef.current || !cameraRef.current || !sceneRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    const y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(new THREE.Vector2(x, y), cameraRef.current);
    const intersects = raycaster.intersectObjects(sceneRef.current.children, true);

    if (intersects.length > 0) {
      const hitPt = intersects[0].point;
      setRulerPoints((prev) => {
        if (prev.length >= 2) return [hitPt];
        const next = [...prev, hitPt];
        if (next.length === 2) {
          const dist = Math.round(next[0].distanceTo(next[1]) * 100) / 100;
          setRulerDistance(dist);
        }
        return next;
      });
    }
  }

  return (
    <div className="bg-paper border border-ink/10 rounded-sm shadow-sm overflow-hidden text-ink">
      {/* Top Header & Tab Switcher */}
      <div className="p-4 bg-mist/30 border-b border-ink/10 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-pine font-bold text-xs uppercase tracking-wider">Three.js · BIM Digital Twin</span>
            <h2 className="font-serif text-lg font-bold">
              {isKk ? "3D BIM моделі және жұмыс сызбалары" : "Интерактивная 3D BIM модель и рабочие чертежи"}
            </h2>
          </div>
          <p className="text-xs text-ink/60 mt-0.5">
            {projectTitle} · {isKk ? "АР / КЖ / ОВ / ВК бөлімдері" : "Разделы АР / КЖ / ОВ / ВК · Инженерные слои и сечения"}
          </p>
        </div>

        {/* 3D Model vs 2D CAD Sheets Switcher */}
        <div className="flex items-center gap-2">
          <div className="inline-flex border border-ink/15 rounded bg-paper p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setActiveTab("3d")}
              className={`px-3 py-1 rounded transition-colors font-medium flex items-center gap-1.5 ${
                activeTab === "3d" ? "bg-pine text-paper shadow-xs" : "text-ink/70 hover:bg-mist"
              }`}
            >
              <span>🏢</span>
              <span>{isKk ? "3D BIM Модель" : "3D BIM Модель"}</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("2d")}
              className={`px-3 py-1 rounded transition-colors font-medium flex items-center gap-1.5 ${
                activeTab === "2d" ? "bg-pine text-paper shadow-xs" : "text-ink/70 hover:bg-mist"
              }`}
            >
              <span>📐</span>
              <span>{isKk ? "2D Сызбалар жинағы" : "2D Чертежи (Комплект)"}</span>
              <span className="ml-1 px-1 py-0.2 rounded bg-ink/10 text-[10px]">{drawings.length}</span>
            </button>
          </div>
        </div>
      </div>

      {activeTab === "3d" ? (
        <div className="grid grid-cols-1 lg:grid-cols-12 border-t border-ink/10">
          {/* Left Controls & Layers Panel (3 cols) */}
          <div className="lg:col-span-3 p-4 border-r border-ink/10 bg-paper space-y-4 text-xs overflow-y-auto max-h-[620px]">
            {/* Camera Presets */}
            <div>
              <label className="block font-semibold uppercase tracking-wider text-[10px] text-ink/50 mb-2">
                {isKk ? "Камера бұрыштары" : "Проекция камеры"}
              </label>
              <div className="grid grid-cols-2 gap-1.5">
                <button
                  type="button"
                  onClick={() => setCameraPreset("iso")}
                  className="py-1 px-2 rounded border border-ink/15 text-center hover:bg-mist font-medium"
                >
                  Isometric 3D
                </button>
                <button
                  type="button"
                  onClick={() => setCameraPreset("top")}
                  className="py-1 px-2 rounded border border-ink/15 text-center hover:bg-mist font-medium"
                >
                  План (Сверху)
                </button>
                <button
                  type="button"
                  onClick={() => setCameraPreset("front")}
                  className="py-1 px-2 rounded border border-ink/15 text-center hover:bg-mist font-medium"
                >
                  Фасад главный
                </button>
                <button
                  type="button"
                  onClick={() => setCameraPreset("side")}
                  className="py-1 px-2 rounded border border-ink/15 text-center hover:bg-mist font-medium"
                >
                  Фасад боковой
                </button>
              </div>
            </div>

            {/* Render Styles */}
            <div className="border-t border-ink/10 pt-3">
              <label className="block font-semibold uppercase tracking-wider text-[10px] text-ink/50 mb-2">
                {isKk ? "Көрініс режимі" : "Режим визуализации"}
              </label>
              <div className="grid grid-cols-2 gap-1.5">
                <button
                  type="button"
                  onClick={() => setRenderMode("realistic")}
                  className={`py-1 px-2 rounded border text-center font-medium ${
                    renderMode === "realistic" ? "bg-pine text-paper border-pine" : "border-ink/15 hover:bg-mist"
                  }`}
                >
                  Реалистичный
                </button>
                <button
                  type="button"
                  onClick={() => setRenderMode("wireframe")}
                  className={`py-1 px-2 rounded border text-center font-medium ${
                    renderMode === "wireframe" ? "bg-pine text-paper border-pine" : "border-ink/15 hover:bg-mist"
                  }`}
                >
                  Каркас (CAD)
                </button>
                <button
                  type="button"
                  onClick={() => setRenderMode("xray")}
                  className={`py-1 px-2 rounded border text-center font-medium ${
                    renderMode === "xray" ? "bg-pine text-paper border-pine" : "border-ink/15 hover:bg-mist"
                  }`}
                >
                  Рентген (X-Ray)
                </button>
                <button
                  type="button"
                  onClick={() => setRenderMode("blueprint")}
                  className={`py-1 px-2 rounded border text-center font-medium ${
                    renderMode === "blueprint" ? "bg-pine text-paper border-pine" : "border-ink/15 hover:bg-mist"
                  }`}
                >
                  Синька (Blueprint)
                </button>
              </div>
            </div>

            {/* Vertical Clipping Plane (Сечение этажей) */}
            <div className="border-t border-ink/10 pt-3">
              <div className="flex justify-between items-center mb-1">
                <label className="font-semibold uppercase tracking-wider text-[10px] text-ink/50">
                  {isKk ? "Биіктік қимасы (Слайдер)" : "Сечение по высоте (Clipping)"}
                </label>
                <span className="font-bold text-pine">{clipHeight.toFixed(1)} м</span>
              </div>
              <input
                type="range"
                min="0.2"
                max="9.0"
                step="0.1"
                value={clipHeight}
                onChange={(e) => setClipHeight(Number(e.target.value))}
                className="w-full accent-pine cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-ink/40 mt-0.5">
                <span>Фундамент</span>
                <span>1 этаж (3.2м)</span>
                <span>2 этаж (6.4м)</span>
                <span>Кровля</span>
              </div>
            </div>

            {/* BIM Layer Toggles */}
            <div className="border-t border-ink/10 pt-3">
              <label className="block font-semibold uppercase tracking-wider text-[10px] text-ink/50 mb-2">
                {isKk ? "BIM Қабаттарын басқару" : "Слои BIM модели (Диспетчер)"}
              </label>
              <div className="space-y-1.5">
                <label className="flex items-center gap-2 cursor-pointer p-1 rounded hover:bg-mist">
                  <input
                    type="checkbox"
                    checked={showArch}
                    onChange={(e) => setShowArch(e.target.checked)}
                    className="accent-pine rounded"
                  />
                  <span className="font-medium">🧱 АР: Архитектурные стены и окна</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer p-1 rounded hover:bg-mist">
                  <input
                    type="checkbox"
                    checked={showConcrete}
                    onChange={(e) => setShowConcrete(e.target.checked)}
                    className="accent-pine rounded"
                  />
                  <span className="font-medium">🏗️ КЖ: Фундамент и перекрытия</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer p-1 rounded hover:bg-mist">
                  <input
                    type="checkbox"
                    checked={showRoof}
                    onChange={(e) => setShowRoof(e.target.checked)}
                    className="accent-pine rounded"
                  />
                  <span className="font-medium">🏠 КР: Кровля и стропила</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer p-1 rounded hover:bg-mist">
                  <input
                    type="checkbox"
                    checked={showMep}
                    onChange={(e) => setShowMep(e.target.checked)}
                    className="accent-pine rounded"
                  />
                  <span className="font-medium">⚡ ОВ/ВК: Теплый пол, канализация, ОВ</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer p-1 rounded hover:bg-mist">
                  <input
                    type="checkbox"
                    checked={showRebar}
                    onChange={(e) => setShowRebar(e.target.checked)}
                    className="accent-pine rounded"
                  />
                  <span className="font-medium">⛓️ Арматурный каркас (А500С)</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer p-1 rounded hover:bg-mist">
                  <input
                    type="checkbox"
                    checked={showMarkers}
                    onChange={(e) => setShowMarkers(e.target.checked)}
                    className="accent-pine rounded"
                  />
                  <span className="font-medium">🚩 Метки технадзора (RFI/PUNCH)</span>
                </label>
              </div>
            </div>

            {/* 3D Ruler Tool */}
            <div className="border-t border-ink/10 pt-3">
              <div className="flex items-center justify-between mb-1.5">
                <label className="font-semibold uppercase tracking-wider text-[10px] text-ink/50">
                  {isKk ? "3D Лазерлік сызғыш" : "3D Лазерная рулетка"}
                </label>
                <button
                  type="button"
                  onClick={() => {
                    setRulerActive(!rulerActive);
                    setRulerPoints([]);
                    setRulerDistance(null);
                  }}
                  className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${
                    rulerActive
                      ? "bg-amber-600 text-paper border-amber-600 shadow-xs"
                      : "border-ink/20 text-ink/70 hover:bg-mist"
                  }`}
                >
                  {rulerActive ? "Активна (Клик по модели)" : "Включить замер"}
                </button>
              </div>
              {rulerActive && (
                <p className="text-[11px] text-amber-800 bg-amber-50 p-2 rounded border border-amber-200">
                  👉 Кликните две точки на 3D модели для замера габарита
                  {rulerDistance !== null && (
                    <strong className="block mt-1 text-xs text-amber-950 font-bold">
                      Расстояние: {rulerDistance} метров
                    </strong>
                  )}
                </p>
              )}
            </div>
          </div>

          {/* Right 3D Canvas Viewport (9 cols) */}
          <div className="lg:col-span-9 relative bg-[#F4F6F9] select-none min-h-[520px]">
            <div
              ref={containerRef}
              onClick={handleCanvasClick}
              className="w-full h-full absolute inset-0 cursor-grab active:cursor-grabbing"
            />

            {/* Floating Navigation & Compass HUD */}
            <div className="absolute top-3 left-3 z-10 bg-paper/85 backdrop-blur-xs p-2.5 rounded shadow-sm border border-ink/10 text-xs space-y-1 pointer-events-none">
              <p className="font-semibold text-ink flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-pine animate-pulse" />
                <span>ANYQ 3D BIM Viewer v2.4</span>
              </p>
              <p className="text-[10px] text-ink/60">
                ЛКМ: Вращение · ПКМ: Панорамирование · Колесо: Зум
              </p>
            </div>

            {/* Quick Dimension Specs Bar */}
            <div className="absolute bottom-3 left-3 right-3 z-10 bg-paper/90 backdrop-blur-xs p-2.5 rounded shadow border border-ink/10 flex flex-wrap items-center justify-between text-xs gap-3">
              <div className="flex flex-wrap items-center gap-4">
                <div>
                  <span className="text-ink/45 text-[10px] block">Габариты здания:</span>
                  <span className="font-bold">12.0 × 9.6 × 8.85 м</span>
                </div>
                <div>
                  <span className="text-ink/45 text-[10px] block">Площадь застройки:</span>
                  <span className="font-bold text-pine">115.2 м²</span>
                </div>
                <div>
                  <span className="text-ink/45 text-[10px] block">Общая площадь:</span>
                  <span className="font-bold">184.6 м² (2 этажа)</span>
                </div>
                <div>
                  <span className="text-ink/45 text-[10px] block">Объем бетона КЖ:</span>
                  <span className="font-bold">48.2 м³</span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setCameraPreset("iso")}
                  className="px-2.5 py-1 bg-mist/60 hover:bg-mist rounded border border-ink/15 text-[11px] font-medium"
                >
                  Сбросить камеру
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <PdfDrawingViewer
          locale={locale}
          drawings={drawings}
          selectedDrawing={selectedDrawing}
          onSelectDrawing={setSelectedDrawing}
          projectTitle={projectTitle}
        />
      )}
    </div>
  );
}
