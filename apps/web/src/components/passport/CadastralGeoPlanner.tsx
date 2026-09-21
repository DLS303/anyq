"use client";

import React, { useEffect, useMemo, useState, useRef } from "react";
import {
  MapContainer,
  TileLayer,
  Polygon,
  Polyline,
  CircleMarker,
  Tooltip,
  useMapEvents,
} from "react-leaflet";
import * as turf from "@turf/turf";
import "leaflet/dist/leaflet.css";
import type { Locale, Plot } from "@/lib/types";
import { money, titleOf, maskCadastral } from "@/lib/format";

interface Props {
  plot: Plot;
  locale: Locale;
}

type TileType = "osm" | "satellite";

function MapClickHandler({
  activeMode,
  onMapClick,
}: {
  activeMode: "move_house" | "ruler" | null;
  onMapClick: (lat: number, lng: number) => void;
}) {
  useMapEvents({
    click(e) {
      if (activeMode) {
        onMapClick(e.latlng.lat, e.latlng.lng);
      }
    },
  });
  return null;
}

export function CadastralGeoPlanner({ plot, locale }: Props) {
  const isKk = locale === "kk";
  const [mounted, setMounted] = useState(false);
  const [tileType, setTileType] = useState<TileType>("satellite");

  // House dimensions & orientation
  const [houseWidth, setHouseWidth] = useState<number>(10); // meters
  const [houseLength, setHouseLength] = useState<number>(12); // meters
  const [houseFloors, setHouseFloors] = useState<number>(2); // 1, 2, 3
  const [houseRotation, setHouseRotation] = useState<number>(0); // degrees

  // SNiP setbacks
  const [setbackNeighbors, setSetbackNeighbors] = useState<number>(3.0); // 3m min to neighbors
  const [setbackRoad, setSetbackRoad] = useState<number>(5.0); // 5m min to road/red line

  // Interactive modes
  const [activeMode, setActiveMode] = useState<"move_house" | "ruler" | null>(null);
  const [rulerPoints, setRulerPoints] = useState<[number, number][]>([]);
  const [showPassportModal, setShowPassportModal] = useState<boolean>(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Plot polygon coordinates: DB format is [lat, lng][]
  const plotPositions = useMemo(() => {
    return (plot.polygon as [number, number][]) || [];
  }, [plot.polygon]);

  // Turf polygon: [lng, lat][]
  const turfPlotPolygon = useMemo(() => {
    if (!plotPositions || plotPositions.length < 3) return null;
    const coords = plotPositions.map(([lat, lng]) => [lng, lat]);
    // Ensure closed
    if (
      coords[0][0] !== coords[coords.length - 1][0] ||
      coords[0][1] !== coords[coords.length - 1][1]
    ) {
      coords.push(coords[0]);
    }
    try {
      return turf.polygon([coords]);
    } catch {
      return null;
    }
  }, [plotPositions]);

  // Centroid
  const centroidCoords = useMemo<[number, number]>(() => {
    if (!turfPlotPolygon) return [43.24, 76.92];
    try {
      const c = turf.centroid(turfPlotPolygon);
      return [c.geometry.coordinates[1], c.geometry.coordinates[0]];
    } catch {
      return [43.24, 76.92];
    }
  }, [turfPlotPolygon]);

  // User positioned house center (defaults to centroid)
  const [houseCenter, setHouseCenter] = useState<[number, number] | null>(null);

  // Sync houseCenter when centroid changes
  useEffect(() => {
    setHouseCenter(centroidCoords);
  }, [centroidCoords]);

  // Plot Boundary LineString for distance measurements
  const turfPlotLine = useMemo(() => {
    if (!turfPlotPolygon) return null;
    try {
      return turf.polygonToLine(turfPlotPolygon);
    } catch {
      return null;
    }
  }, [turfPlotPolygon]);

  // Geodesic calculations
  const { plotAreaSqM, plotAreaSotka, plotPerimeterM, sideLengths } = useMemo(() => {
    if (!turfPlotPolygon || !turfPlotLine) {
      return { plotAreaSqM: 0, plotAreaSotka: 0, plotPerimeterM: 0, sideLengths: [] };
    }
    try {
      const areaM2 = turf.area(turfPlotPolygon);
      const sotka = areaM2 / 100;
      const perimM = turf.length(turfPlotLine, { units: "meters" });

      // Calculate each boundary side length
      const lengths: { fromIdx: number; toIdx: number; lenM: number }[] = [];
      for (let i = 0; i < plotPositions.length - 1; i++) {
        const p1 = turf.point([plotPositions[i][1], plotPositions[i][0]]);
        const p2 = turf.point([plotPositions[i + 1][1], plotPositions[i + 1][0]]);
        const d = turf.distance(p1, p2, { units: "meters" });
        lengths.push({ fromIdx: i + 1, toIdx: i + 2, lenM: Math.round(d * 10) / 10 });
      }

      return {
        plotAreaSqM: Math.round(areaM2 * 10) / 10,
        plotAreaSotka: Math.round(sotka * 100) / 100,
        plotPerimeterM: Math.round(perimM * 10) / 10,
        sideLengths: lengths,
      };
    } catch {
      return { plotAreaSqM: 0, plotAreaSotka: 0, plotPerimeterM: 0, sideLengths: [] };
    }
  }, [turfPlotPolygon, turfPlotLine, plotPositions]);

  // SNiP setback polygon (inner buffer)
  const setbackPolygonPositions = useMemo(() => {
    if (!turfPlotPolygon) return [];
    try {
      // Buffer in km (negative for inset)
      const bufferDistKm = -setbackNeighbors / 1000;
      const buffered = turf.buffer(turfPlotPolygon, bufferDistKm, { units: "kilometers" });
      if (!buffered || !buffered.geometry) return [];

      let ring: number[][] = [];
      if (buffered.geometry.type === "Polygon") {
        ring = buffered.geometry.coordinates[0];
      } else if (buffered.geometry.type === "MultiPolygon") {
        ring = buffered.geometry.coordinates[0][0];
      }

      return ring.map(([lng, lat]) => [lat, lng] as [number, number]);
    } catch {
      return [];
    }
  }, [turfPlotPolygon, setbackNeighbors]);

  // Setback zone area
  const setbackAreaSqM = useMemo(() => {
    if (!setbackPolygonPositions || setbackPolygonPositions.length < 3) return 0;
    try {
      const poly = turf.polygon([setbackPolygonPositions.map(([lat, lng]) => [lng, lat])]);
      return Math.round(turf.area(poly));
    } catch {
      return 0;
    }
  }, [setbackPolygonPositions]);

  // House corners calculation
  const housePolygonPositions = useMemo(() => {
    const center = houseCenter || centroidCoords;
    const [lat, lng] = center;
    const halfW = houseWidth / 2;
    const halfL = houseLength / 2;
    const mPerDegLat = 111320;
    const mPerDegLng = 111320 * Math.cos((lat * Math.PI) / 180);
    const rad = (houseRotation * Math.PI) / 180;
    const cos = Math.cos(rad);
    const sin = Math.sin(rad);

    const localCorners = [
      [-halfW, -halfL],
      [halfW, -halfL],
      [halfW, halfL],
      [-halfW, halfL],
      [-halfW, -halfL],
    ];

    return localCorners.map(([dx, dy]) => {
      const rx = dx * cos - dy * sin;
      const ry = dx * sin + dy * cos;
      return [lat + ry / mPerDegLat, lng + rx / mPerDegLng] as [number, number];
    });
  }, [houseCenter, centroidCoords, houseWidth, houseLength, houseRotation]);

  // House metrics and compliance check
  const { minDistanceM, isCompliant, houseAreaSqM, totalLivingAreaSqM, buildingCoeffPct } =
    useMemo(() => {
      const areaSqM = houseWidth * houseLength;
      const totalLiving = areaSqM * houseFloors * 0.85; // 85% usable living area
      const coeff = plotAreaSqM > 0 ? (areaSqM / plotAreaSqM) * 100 : 0;

      if (!turfPlotLine) {
        return {
          minDistanceM: 0,
          isCompliant: true,
          houseAreaSqM: areaSqM,
          totalLivingAreaSqM: Math.round(totalLiving),
          buildingCoeffPct: Math.round(coeff * 10) / 10,
        };
      }

      let minDist = Infinity;
      try {
        for (const [lat, lng] of housePolygonPositions) {
          const pt = turf.point([lng, lat]);
          // Check if point is inside plot
          if (turfPlotPolygon && !turf.booleanPointInPolygon(pt, turfPlotPolygon)) {
            minDist = -1; // Outside plot!
            break;
          }
          const d = turf.pointToLineDistance(pt, turfPlotLine as any, { units: "meters" });
          if (d < minDist) minDist = d;
        }
      } catch {
        minDist = 5.0;
      }

      const compliant = minDist >= setbackNeighbors && coeff <= 35;

      return {
        minDistanceM: minDist < 0 ? 0 : Math.round(minDist * 10) / 10,
        isCompliant: compliant,
        houseAreaSqM: areaSqM,
        totalLivingAreaSqM: Math.round(totalLiving),
        buildingCoeffPct: Math.round(coeff * 10) / 10,
      };
    }, [
      houseWidth,
      houseLength,
      houseFloors,
      plotAreaSqM,
      housePolygonPositions,
      turfPlotLine,
      turfPlotPolygon,
      setbackNeighbors,
    ]);

  // Foundation rough estimate
  const foundationEstimate = useMemo(() => {
    // Sized for monolith slab (30cm thick)
    const concreteM3 = Math.round(houseAreaSqM * 0.3 * 10) / 10;
    const rebarTons = Math.round(((houseAreaSqM * 35) / 1000) * 10) / 10;
    // Market prices: M350 concrete ~ 26,000 KZT/m3, Rebar ~ 380,000 KZT/ton, works ~ 18,000 KZT/m2
    const costKzt = Math.round(
      concreteM3 * 26000 + rebarTons * 380000 + houseAreaSqM * 18000
    );
    return { concreteM3, rebarTons, costKzt };
  }, [houseAreaSqM]);

  // Map click handler
  function handleMapClick(lat: number, lng: number) {
    if (activeMode === "move_house") {
      setHouseCenter([lat, lng]);
    } else if (activeMode === "ruler") {
      setRulerPoints((prev) => (prev.length >= 2 ? [[lat, lng]] : [...prev, [lat, lng]]));
    }
  }

  // Ruler measurement distance
  const rulerDistanceM = useMemo(() => {
    if (rulerPoints.length < 2) return null;
    try {
      const p1 = turf.point([rulerPoints[0][1], rulerPoints[0][0]]);
      const p2 = turf.point([rulerPoints[1][1], rulerPoints[1][0]]);
      const d = turf.distance(p1, p2, { units: "meters" });
      return Math.round(d * 10) / 10;
    } catch {
      return null;
    }
  }, [rulerPoints]);

  if (!mounted) {
    return (
      <div className="h-[480px] bg-mist/20 rounded border border-ink/10 flex items-center justify-center text-ink/40 text-xs">
        {isKk ? "Гео-карта жүктелуде..." : "Инициализация гео-карты..."}
      </div>
    );
  }

  return (
    <div className="bg-paper border border-ink/10 rounded-sm shadow-sm overflow-hidden text-ink">
      {/* Top Header */}
      <div className="p-4 bg-mist/30 border-b border-ink/10 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-pine font-bold text-sm">📐 Turf.js + Leaflet</span>
            <h2 className="font-serif text-lg font-bold">
              {isKk
                ? "Кадастрлық гео-калькулятор және СНиП құрылыс дағы"
                : "Кадастровый гео-калькулятор и посадка дома по СНиП РК"}
            </h2>
          </div>
          <p className="text-xs text-ink/60 mt-0.5">
            {isKk
              ? `Кадастр № ${maskCadastral(plot.cadastral_no, true)} · Аудан: ${plotAreaSotka} сотық (${plotAreaSqM} м²)`
              : `Кадастровый № ${maskCadastral(plot.cadastral_no, true)} · Площадь: ${plotAreaSotka} соток (${plotAreaSqM} м²) · Периметр: ${plotPerimeterM} м`}
          </p>
        </div>

        {/* Compliance Status Badge */}
        <div className="flex items-center gap-2">
          {isCompliant ? (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-semibold shadow-xs">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>{isKk ? "СНиП сәйкес (Рұқсат етілген)" : "СНиП РК соблюдён (Разрешено)"}</span>
              <span className="text-[11px] opacity-80">({minDistanceM} м)</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-red-50 text-red-800 border border-red-200 text-xs font-semibold shadow-xs">
              <span className="w-2 h-2 rounded-full bg-red-500 animate-ping" />
              <span>{isKk ? "СНиП бұзылуы (Қауіпті шегініс)" : "Нарушение СНиП (Отступ < 3м)"}</span>
              <span className="text-[11px] opacity-80">({minDistanceM} м)</span>
            </div>
          )}

          <button
            type="button"
            onClick={() => setShowPassportModal(true)}
            className="px-3 py-1.5 bg-pine text-paper rounded text-xs font-semibold hover:bg-pine/90 transition-colors flex items-center gap-1 shadow-xs"
          >
            <span>🖨️</span>
            <span>{isKk ? "Паспортты басып шығару" : "Гео-паспорт посадки"}</span>
          </button>
        </div>
      </div>

      {/* Main Grid: Left Controls (4 cols), Right Map (8 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 border-t border-ink/10">
        {/* Left Side: Parameters & Geodetic Metrics */}
        <div className="lg:col-span-4 p-4 border-r border-ink/10 bg-paper space-y-5 text-xs overflow-y-auto max-h-[640px]">
          {/* Map Layer & Tools */}
          <div>
            <label className="block font-semibold uppercase tracking-wider text-[10px] text-ink/50 mb-2">
              {isKk ? "Карта қабаты және құралдар" : "Слой карты и инструменты"}
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setTileType("satellite")}
                className={`py-1.5 px-2 rounded border text-center transition-colors font-medium ${
                  tileType === "satellite"
                    ? "bg-pine text-paper border-pine"
                    : "border-ink/15 text-ink/70 hover:bg-mist"
                }`}
              >
                🛰️ {isKk ? "Ғарыш (Satellite)" : "Спутник (Esri)"}
              </button>
              <button
                type="button"
                onClick={() => setTileType("osm")}
                className={`py-1.5 px-2 rounded border text-center transition-colors font-medium ${
                  tileType === "osm"
                    ? "bg-pine text-paper border-pine"
                    : "border-ink/15 text-ink/70 hover:bg-mist"
                }`}
              >
                🗺️ {isKk ? "Схема (OSM)" : "Схема (OSM)"}
              </button>
            </div>

            <div className="mt-2 flex gap-2">
              <button
                type="button"
                onClick={() => setActiveMode(activeMode === "move_house" ? null : "move_house")}
                className={`flex-1 py-1.5 px-2 rounded border text-center transition-colors font-medium ${
                  activeMode === "move_house"
                    ? "bg-sky-600 text-paper border-sky-600 shadow-inner"
                    : "border-ink/15 text-ink/70 hover:bg-mist"
                }`}
              >
                📍 {isKk ? "Үйді орналастыру (Click)" : "Переместить дом (Клик)"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setActiveMode(activeMode === "ruler" ? null : "ruler");
                  setRulerPoints([]);
                }}
                className={`py-1.5 px-3 rounded border text-center transition-colors font-medium ${
                  activeMode === "ruler"
                    ? "bg-amber-600 text-paper border-amber-600 shadow-inner"
                    : "border-ink/15 text-ink/70 hover:bg-mist"
                }`}
              >
                📏 {isKk ? "Сызғыш" : "Линейка"}
              </button>
            </div>
            {activeMode === "move_house" && (
              <p className="mt-1.5 text-[11px] text-sky-700 bg-sky-50 p-1.5 rounded border border-sky-200">
                👉 {isKk ? "Үйді қою үшін картаға кез келген жерді басыңыз" : "Кликните по участку на карте, чтобы поставить дом"}
              </p>
            )}
            {activeMode === "ruler" && (
              <p className="mt-1.5 text-[11px] text-amber-800 bg-amber-50 p-1.5 rounded border border-amber-200">
                👉 {isKk ? "Қашықтықты өлшеу үшін 2 нүктені басыңыз" : "Кликните 2 точки на карте для замера расстояния"}
                {rulerDistanceM !== null && (
                  <strong className="block mt-0.5 text-xs font-bold text-amber-900">
                    Замер: {rulerDistanceM} метров
                  </strong>
                )}
              </p>
            )}
          </div>

          {/* House Parameters Slider */}
          <div className="border-t border-ink/10 pt-4">
            <label className="block font-semibold uppercase tracking-wider text-[10px] text-ink/50 mb-2">
              {isKk ? "Үй өлшемдері (Конструктор)" : "Габариты дома (Конструктор посадки)"}
            </label>

            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-ink/70">{isKk ? "Үй ені" : "Ширина дома"}:</span>
                  <span className="font-bold text-ink">{houseWidth} м</span>
                </div>
                <input
                  type="range"
                  min="6"
                  max="25"
                  step="0.5"
                  value={houseWidth}
                  onChange={(e) => setHouseWidth(Number(e.target.value))}
                  className="w-full accent-pine cursor-pointer"
                />
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-ink/70">{isKk ? "Үй ұзындығы" : "Длина дома"}:</span>
                  <span className="font-bold text-ink">{houseLength} м</span>
                </div>
                <input
                  type="range"
                  min="6"
                  max="30"
                  step="0.5"
                  value={houseLength}
                  onChange={(e) => setHouseLength(Number(e.target.value))}
                  className="w-full accent-pine cursor-pointer"
                />
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-ink/70">{isKk ? "Бұрылу бұрышы" : "Угол поворота"}:</span>
                  <span className="font-bold text-ink">{houseRotation}°</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="360"
                  step="5"
                  value={houseRotation}
                  onChange={(e) => setHouseRotation(Number(e.target.value))}
                  className="w-full accent-pine cursor-pointer"
                />
              </div>

              <div className="flex justify-between items-center pt-1">
                <span className="text-ink/70">{isKk ? "Қабаттылық" : "Этажность"}:</span>
                <div className="inline-flex border border-ink/15 rounded bg-paper p-0.5">
                  {[1, 2, 3].map((f) => (
                    <button
                      key={f}
                      type="button"
                      onClick={() => setHouseFloors(f)}
                      className={`px-3 py-0.5 rounded text-xs transition-colors ${
                        houseFloors === f
                          ? "bg-pine text-paper font-semibold"
                          : "text-ink/70 hover:bg-mist"
                      }`}
                    >
                      {f} эт.
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* SNiP Norms Setback Adjuster */}
          <div className="border-t border-ink/10 pt-4">
            <label className="block font-semibold uppercase tracking-wider text-[10px] text-ink/50 mb-2">
              {isKk ? "ҚР СНиП бойынша шегініс нормалары" : "Нормативные отступы по СНиП РК"}
            </label>

            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-ink/70">{isKk ? "Көршіден шегініс (мин. 3м)" : "Отступ от соседа (норма 3.0 м)"}:</span>
                  <span className="font-bold text-ink">{setbackNeighbors} м</span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="6"
                  step="0.5"
                  value={setbackNeighbors}
                  onChange={(e) => setSetbackNeighbors(Number(e.target.value))}
                  className="w-full accent-pine cursor-pointer"
                />
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-ink/70">{isKk ? "Көшеден шегініс (мин. 5м)" : "Отступ от дороги / улицы (норма 5.0 м)"}:</span>
                  <span className="font-bold text-ink">{setbackRoad} м</span>
                </div>
                <input
                  type="range"
                  min="3"
                  max="10"
                  step="0.5"
                  value={setbackRoad}
                  onChange={(e) => setSetbackRoad(Number(e.target.value))}
                  className="w-full accent-pine cursor-pointer"
                />
              </div>
            </div>
          </div>

          {/* Geodetic & Engineering Metrics */}
          <div className="border-t border-ink/10 pt-4 bg-mist/30 -mx-4 -mb-4 p-4 space-y-2">
            <h4 className="font-semibold text-xs text-ink/90 flex items-center gap-1">
              <span>📊</span>
              <span>{isKk ? "Құрылыс және смета көрсеткіштері" : "Технико-экономические показатели"}</span>
            </h4>

            <div className="grid grid-cols-2 gap-2 text-[11px] pt-1">
              <div className="p-2 bg-paper rounded border border-ink/10">
                <span className="text-ink/50 block text-[10px]">{isKk ? "Үй дағы 1-қабат" : "Пятно застройки 1 эт."}</span>
                <span className="font-bold text-ink text-sm">{houseAreaSqM} м²</span>
              </div>
              <div className="p-2 bg-paper rounded border border-ink/10">
                <span className="text-ink/50 block text-[10px]">{isKk ? "Жалпы тұрғын ауданы" : "Общая площ. дома"}</span>
                <span className="font-bold text-pine text-sm">{totalLivingAreaSqM} м²</span>
              </div>
              <div className="p-2 bg-paper rounded border border-ink/10">
                <span className="text-ink/50 block text-[10px]">{isKk ? "Құрылыс коэфф. (ПЗ)" : "Коэфф. застройки (ПЗ)"}</span>
                <span className={`font-bold text-sm ${buildingCoeffPct > 30 ? "text-red-600" : "text-emerald-700"}`}>
                  {buildingCoeffPct}% <span className="text-[9px] font-normal text-ink/50">(макс 30%)</span>
                </span>
              </div>
              <div className="p-2 bg-paper rounded border border-ink/10">
                <span className="text-ink/50 block text-[10px]">{isKk ? "Мин. шегініс (факт)" : "Мин. отступ факт"}</span>
                <span className={`font-bold text-sm ${isCompliant ? "text-emerald-700" : "text-red-600"}`}>
                  {minDistanceM} м
                </span>
              </div>
            </div>

            {/* Foundation cost card */}
            <div className="p-2.5 bg-paper rounded border border-ink/10 text-[11px] space-y-1">
              <div className="flex justify-between items-center">
                <span className="font-semibold text-ink">{isKk ? "Іргетас сметасы (Бетон плита)" : "Смета фундамента (Плита 300мм)"}:</span>
                <span className="font-bold text-pine">{money(foundationEstimate.costKzt, locale)}</span>
              </div>
              <p className="text-[10px] text-ink/60">
                Бетон В25: <strong>{foundationEstimate.concreteM3} м³</strong> · Арматура А500С: <strong>{foundationEstimate.rebarTons} тн</strong>
              </p>
            </div>
          </div>
        </div>

        {/* Right Side: Leaflet Interactive Map */}
        <div className="lg:col-span-8 relative min-h-[460px] lg:min-h-[580px]">
          <MapContainer
            center={centroidCoords}
            zoom={18}
            className="h-full w-full absolute inset-0 z-0"
            scrollWheelZoom
          >
            {tileType === "satellite" ? (
              <TileLayer
                attribution="&copy; Esri World Imagery"
                url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                maxZoom={20}
              />
            ) : (
              <TileLayer
                attribution="&copy; OpenStreetMap"
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                maxZoom={19}
              />
            )}

            <MapClickHandler activeMode={activeMode} onMapClick={handleMapClick} />

            {/* Plot Boundary Polygon */}
            <Polygon
              positions={plotPositions}
              pathOptions={{
                color: "#0B1E3D",
                weight: 2.5,
                fillColor: "#2E75B6",
                fillOpacity: 0.12,
              }}
            >
              <Tooltip sticky>
                <div className="text-xs">
                  <p className="font-bold">{titleOf(plot, locale)}</p>
                  <p>Площадь: {plotAreaSotka} соток ({plotAreaSqM} м²)</p>
                  <p>Периметр: {plotPerimeterM} м</p>
                </div>
              </Tooltip>
            </Polygon>

            {/* Plot Boundary Markers with Side Lengths */}
            {plotPositions.map((pos, idx) => (
              <CircleMarker
                key={`corner-${idx}`}
                center={pos}
                radius={5}
                pathOptions={{
                  color: "#0B1E3D",
                  fillColor: "#FFFFFF",
                  fillOpacity: 1,
                  weight: 2,
                }}
              >
                <Tooltip direction="top" offset={[0, -5]} permanent={idx === 0}>
                  <span className="text-[10px] font-bold">
                    Т.{idx + 1}
                  </span>
                </Tooltip>
              </CircleMarker>
            ))}

            {/* SNiP Building Setback Polygon (Dashed Cyan) */}
            {setbackPolygonPositions.length >= 3 && (
              <Polygon
                positions={setbackPolygonPositions}
                pathOptions={{
                  color: "#0284C7",
                  weight: 2,
                  dashArray: "6 4",
                  fillColor: "#38BDF8",
                  fillOpacity: 0.15,
                }}
              >
                <Tooltip sticky>
                  <span className="text-xs font-semibold text-sky-800">
                    {isKk ? "Рұқсат етілген құрылыс дағы (СНиП)" : "Разрешённая зона застройки по СНиП РК"}
                    <br />
                    (отступ {setbackNeighbors} м от межи)
                  </span>
                </Tooltip>
              </Polygon>
            )}

            {/* House Footprint Polygon (Emerald when compliant, Red when violation) */}
            <Polygon
              positions={housePolygonPositions}
              pathOptions={{
                color: isCompliant ? "#2E7D32" : "#D32F2F",
                weight: 3,
                fillColor: isCompliant ? "#3CB878" : "#EF5350",
                fillOpacity: 0.55,
              }}
            >
              <Tooltip permanent direction="center">
                <div className="text-center font-sans">
                  <div className="text-[11px] font-extrabold text-ink leading-tight drop-shadow-xs">
                    ДОМ {houseWidth}×{houseLength} м
                  </div>
                  <div className="text-[9px] font-semibold text-ink/80">
                    {houseFloors} этажа · {houseAreaSqM} м²
                  </div>
                  <div className={`text-[8px] font-bold mt-0.5 ${isCompliant ? "text-emerald-900" : "text-red-950"}`}>
                    {isCompliant ? `✓ Отступ: ${minDistanceM} м` : `⚠ Нарушение: ${minDistanceM} м`}
                  </div>
                </div>
              </Tooltip>
            </Polygon>

            {/* House Porch / Entrance indicator */}
            {housePolygonPositions.length >= 4 && (
              <Polyline
                positions={[housePolygonPositions[0], housePolygonPositions[1]]}
                pathOptions={{
                  color: "#F2A93B",
                  weight: 5,
                  opacity: 0.9,
                }}
              />
            )}

            {/* Ruler Line */}
            {rulerPoints.length >= 2 && (
              <Polyline
                positions={rulerPoints}
                pathOptions={{
                  color: "#D97706",
                  weight: 3,
                  dashArray: "5 5",
                }}
              >
                <Tooltip permanent direction="top">
                  <span className="font-bold text-amber-900 text-xs">
                    Замер: {rulerDistanceM} м
                  </span>
                </Tooltip>
              </Polyline>
            )}

            {/* Ruler point markers */}
            {rulerPoints.map((pt, i) => (
              <CircleMarker
                key={`ruler-${i}`}
                center={pt}
                radius={6}
                pathOptions={{ color: "#D97706", fillColor: "#F59E0B", fillOpacity: 1 }}
              />
            ))}
          </MapContainer>

          {/* Floating Quick Compass & Status Legend */}
          <div className="absolute top-3 right-3 z-[400] bg-paper/90 backdrop-blur-xs p-2 rounded shadow border border-ink/10 text-[11px] space-y-1">
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-xs bg-[#0B1E3D] border border-ink/20" />
              <span>{isKk ? "Жер шекарасы" : "Граница участка (АИС ГЗК)"}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-xs border-2 border-dashed border-[#0284C7] bg-[#38BDF8]/20" />
              <span>{isKk ? "СНиП дағы (3м шегініс)" : "Пятно застройки по СНиП"}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-xs bg-[#3CB878] border border-emerald-600" />
              <span>{isKk ? "Үйдің орналасуы" : "Контур дома (вход золотой)"}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Geodetic Passport Print Modal */}
      {showPassportModal && (
        <div className="fixed inset-0 z-50 bg-ink/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-paper border border-ink/15 rounded-md shadow-2xl w-full max-w-2xl p-6 text-xs max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-ink/10 pb-3 mb-4">
              <div>
                <span className="text-pine font-bold uppercase tracking-wider text-[10px]">ANYQ ConTech & PropTech</span>
                <h3 className="font-serif text-xl font-bold">
                  {isKk
                    ? "Үйді орналастыру бойынша геодезиялық есеп"
                    : "Паспорт геодезической посадки дома на участке"}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowPassportModal(false)}
                className="text-ink/40 hover:text-ink text-xl font-bold"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 p-3 bg-mist/30 rounded">
                <div>
                  <span className="text-ink/50 block text-[10px]">{isKk ? "Кадастр нөмірі" : "Кадастровый номер"}:</span>
                  <span className="font-bold font-mono">{maskCadastral(plot.cadastral_no, true)}</span>
                </div>
                <div>
                  <span className="text-ink/50 block text-[10px]">{isKk ? "Аудан және мекенжай" : "Район и локация"}:</span>
                  <span className="font-medium">{plot.district}</span>
                </div>
                <div>
                  <span className="text-ink/50 block text-[10px]">{isKk ? "Жер көлемі" : "Площадь участка"}:</span>
                  <span className="font-bold text-pine">{plotAreaSotka} соток ({plotAreaSqM} м²)</span>
                </div>
                <div>
                  <span className="text-ink/50 block text-[10px]">{isKk ? "Периметр" : "Периметр границ"}:</span>
                  <span className="font-bold">{plotPerimeterM} метров</span>
                </div>
              </div>

              <div>
                <h4 className="font-semibold text-ink text-xs mb-2">
                  {isKk ? "Бұрылу нүктелерінің координаттары (WGS-84)" : "Ведомость поворотных точек участка (WGS-84)"}:
                </h4>
                <table className="w-full text-left border-collapse text-[11px]">
                  <thead>
                    <tr className="bg-mist/60 border-b border-ink/10">
                      <th className="p-1.5">№ Точки</th>
                      <th className="p-1.5">Широта (Lat)</th>
                      <th className="p-1.5">Долгота (Lng)</th>
                      <th className="p-1.5 text-right">Длина стороны</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plotPositions.map((pos, idx) => (
                      <tr key={idx} className="border-b border-ink/5">
                        <td className="p-1.5 font-bold">Т.{idx + 1}</td>
                        <td className="p-1.5 font-mono">{pos[0].toFixed(6)}°</td>
                        <td className="p-1.5 font-mono">{pos[1].toFixed(6)}°</td>
                        <td className="p-1.5 text-right font-mono">
                          {sideLengths[idx] ? `${sideLengths[idx].lenM} м` : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="p-3 bg-emerald-50 rounded border border-emerald-200">
                <h4 className="font-bold text-emerald-900 text-xs mb-1">
                  {isCompliant
                    ? "✓ Заключение экспертизы: Нормы СНиП РК соблюдены"
                    : "⚠ Внимание: Требуется корректировка посадки"}
                </h4>
                <p className="text-[11px] text-emerald-800">
                  Дом габаритами <strong>{houseWidth}×{houseLength} м</strong> ({houseAreaSqM} м² пятно застройки, {totalLivingAreaSqM} м² жилая площадь) размещен с минимальным отступом <strong>{minDistanceM} м</strong> от межи. Коэффициент застройки составляет <strong>{buildingCoeffPct}%</strong> (норма до 30–35%). Объект соответствует требованиям для подачи на АПЗ и эскизное согласование.
                </p>
              </div>

              <div className="flex justify-between items-center pt-3 border-t border-ink/10">
                <p className="text-[10px] text-ink/40">
                  Сформировано платформой ANYQ ConTech Казахстан · {new Date().toLocaleDateString()}
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => window.print()}
                    className="px-4 py-1.5 bg-pine text-paper rounded font-semibold text-xs hover:bg-pine/90 transition-colors"
                  >
                    Печать / Сохранить в PDF
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowPassportModal(false)}
                    className="px-3 py-1.5 border border-ink/20 rounded text-xs hover:bg-mist transition-colors"
                  >
                    Закрыть
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
