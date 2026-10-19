"use client";

import { useState, useMemo } from "react";
import type { Locale } from "@/lib/types";
import { bytesToBlob, saveBlobDownload, XLSX_MIME } from "@/lib/native";

// ─── Types ────────────────────────────────────────────────────────────────────
type UnitStatus = "free" | "reserved" | "sold" | "unavailable" | "construction";

interface Unit {
  id: string;
  section: number;
  floor: number;
  num: string;
  area: number;
  rooms: number;
  price_kzt: number;
  status: UnitStatus;
  client?: string;
  facing: string;
}

interface Building {
  id: string;
  name: string;
  sections: number;
  floors: number;
  units_per_floor: number;
}

// ─── Seed data ────────────────────────────────────────────────────────────────
const BUILDINGS: Building[] = [
  { id: "b1", name: "Корпус 1", sections: 2, floors: 9, units_per_floor: 4 },
  { id: "b2", name: "Корпус 2", sections: 2, floors: 9, units_per_floor: 4 },
  { id: "b3", name: "Таунхаусы", sections: 1, floors: 2, units_per_floor: 6 },
];

const FACINGS = ["N", "S", "E", "W", "NE", "NW", "SE", "SW"];

function seeded(seed: number) {
  let s = seed;
  return () => { s = (s * 16807 + 0) % 2147483647; return (s - 1) / 2147483646; };
}

function generateUnits(): Unit[] {
  const units: Unit[] = [];
  const statuses: UnitStatus[] = ["free", "free", "free", "reserved", "sold", "construction", "unavailable"];
  const roomsArr = [1, 2, 2, 3, 3, 4];
  let counter = 100;
  let seed = 42;

  BUILDINGS.forEach((b) => {
    for (let s = 1; s <= b.sections; s++) {
      for (let f = b.floors; f >= 1; f--) {
        for (let u = 1; u <= b.units_per_floor; u++) {
          counter++;
          seed++;
          const rng = seeded(seed * 1000 + counter);
          const rm = roomsArr[Math.floor(rng() * roomsArr.length)];
          const area = rm * 18 + Math.floor(rng() * 20) + 10;
          const pricePerM2 = 450000 + Math.floor(rng() * 150000);
          const st = statuses[Math.floor(rng() * statuses.length)];
          units.push({
            id: `${b.id}-s${s}-f${f}-u${u}`,
            section: s,
            floor: f,
            num: String(counter),
            area,
            rooms: rm,
            price_kzt: area * pricePerM2,
            status: st,
            client: st === "sold" || st === "reserved" ? `Клиент ${counter}` : undefined,
            facing: FACINGS[Math.floor(rng() * FACINGS.length)],
          });
        }
      }
    }
  });
  return units;
}

const ALL_UNITS = generateUnits();

// ─── Status config ────────────────────────────────────────────────────────────
const STATUS_CFG: Record<UnitStatus, { label: string; bg: string; border: string; text: string; dot: string }> = {
  free:         { label: "Свободно",   bg: "bg-emerald-50",  border: "border-emerald-300", text: "text-emerald-800", dot: "bg-emerald-400" },
  reserved:     { label: "Бронь",      bg: "bg-amber-50",    border: "border-amber-300",   text: "text-amber-800",   dot: "bg-amber-400" },
  sold:         { label: "Продано",    bg: "bg-slate-100",   border: "border-slate-300",   text: "text-slate-500",   dot: "bg-slate-400" },
  unavailable:  { label: "Недоступно", bg: "bg-red-50",      border: "border-red-200",     text: "text-red-400",     dot: "bg-red-300" },
  construction: { label: "Стройка",    bg: "bg-blue-50",     border: "border-blue-200",    text: "text-blue-600",    dot: "bg-blue-400" },
};

function money(v: number) {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)} млн \u20B8`;
  return `${(v / 1_000).toFixed(0)} тыс \u20B8`;
}

// ─── SVG Site Plan ────────────────────────────────────────────────────────────
function SitePlan({ selectedBuilding, onSelect }: { selectedBuilding: string; onSelect: (id: string) => void }) {
  return (
    <div className="relative bg-stone-50 border border-ink/10 rounded-xl overflow-hidden" style={{ height: 320 }}>
      <svg viewBox="0 0 700 320" className="w-full h-full">
        <rect x="0" y="0" width="700" height="320" fill="#f5f5f0" />
        <rect x="0" y="270" width="700" height="50" fill="#d4d0c8" />
        <text x="350" y="298" textAnchor="middle" fontSize="11" fill="#888" fontFamily="sans-serif">ул. Есенберлина</text>
        <rect x="0" y="0" width="40" height="320" fill="#d4d0c8" />
        <rect x="50" y="10" width="640" height="30" fill="#c8e6c9" rx="4" />
        <text x="370" y="29" textAnchor="middle" fontSize="10" fill="#388e3c" fontFamily="sans-serif">Озеленение / бульвар</text>

        <rect x="60" y="60" width="200" height="120" rx="6"
          fill={selectedBuilding === "b1" ? "#1a6b4a" : "#4caf80"}
          stroke={selectedBuilding === "b1" ? "#0f3d2a" : "#388e3c"}
          strokeWidth="2" style={{ cursor: "pointer" }}
          onClick={() => onSelect("b1")} />
        <text x="160" y="115" textAnchor="middle" fontSize="13" fontWeight="bold" fill="white" fontFamily="sans-serif" style={{ cursor: "pointer" }} onClick={() => onSelect("b1")}>Корпус 1</text>
        <text x="160" y="132" textAnchor="middle" fontSize="10" fill="rgba(255,255,255,0.85)" fontFamily="sans-serif" style={{ cursor: "pointer" }} onClick={() => onSelect("b1")}>9 эт · 72 кв</text>

        <rect x="280" y="60" width="200" height="120" rx="6"
          fill={selectedBuilding === "b2" ? "#1a6b4a" : "#4caf80"}
          stroke={selectedBuilding === "b2" ? "#0f3d2a" : "#388e3c"}
          strokeWidth="2" style={{ cursor: "pointer" }}
          onClick={() => onSelect("b2")} />
        <text x="380" y="115" textAnchor="middle" fontSize="13" fontWeight="bold" fill="white" fontFamily="sans-serif" style={{ cursor: "pointer" }} onClick={() => onSelect("b2")}>Корпус 2</text>
        <text x="380" y="132" textAnchor="middle" fontSize="10" fill="rgba(255,255,255,0.85)" fontFamily="sans-serif" style={{ cursor: "pointer" }} onClick={() => onSelect("b2")}>9 эт · 72 кв</text>

        <rect x="500" y="60" width="180" height="80" rx="6"
          fill={selectedBuilding === "b3" ? "#b45309" : "#f59e0b"}
          stroke={selectedBuilding === "b3" ? "#78350f" : "#d97706"}
          strokeWidth="2" style={{ cursor: "pointer" }}
          onClick={() => onSelect("b3")} />
        <text x="590" y="95" textAnchor="middle" fontSize="13" fontWeight="bold" fill="white" fontFamily="sans-serif" style={{ cursor: "pointer" }} onClick={() => onSelect("b3")}>Таунхаусы</text>
        <text x="590" y="112" textAnchor="middle" fontSize="10" fill="rgba(255,255,255,0.85)" fontFamily="sans-serif" style={{ cursor: "pointer" }} onClick={() => onSelect("b3")}>2 эт · 12 ед</text>

        <rect x="60" y="200" width="620" height="55" rx="4" fill="#e0e0e0" stroke="#bdbdbd" strokeWidth="1" />
        <text x="370" y="231" textAnchor="middle" fontSize="11" fill="#555" fontFamily="sans-serif">Паркинг · 120 м/м</text>

        <circle cx="480" cy="155" r="22" fill="#fff9c4" stroke="#f9a825" strokeWidth="1.5" />
        <text x="480" y="150" textAnchor="middle" fontSize="9" fill="#f57f17" fontFamily="sans-serif">Детск.</text>
        <text x="480" y="163" textAnchor="middle" fontSize="8" fill="#f57f17" fontFamily="sans-serif">площ.</text>

        <g transform="translate(660,30)">
          <circle r="18" fill="white" stroke="#ccc" strokeWidth="1" />
          <text textAnchor="middle" y="-4" fontSize="9" fontWeight="bold" fill="#1a6b4a" fontFamily="sans-serif">С</text>
          <text textAnchor="middle" y="12" fontSize="9" fill="#888" fontFamily="sans-serif">Ю</text>
          <line x1="0" y1="-12" x2="0" y2="12" stroke="#ccc" strokeWidth="0.5" />
        </g>
      </svg>
      <div className="absolute top-2 left-2 bg-white/90 rounded-lg px-2 py-1 text-xs text-ink/60 border border-ink/10">
        Генплан · ЖК «Бесагаш Резиденс»
      </div>
      <div className="absolute bottom-2 right-2 text-xs text-ink/40 bg-white/80 px-2 py-0.5 rounded">
        Нажмите на корпус для шахматки
      </div>
    </div>
  );
}

// ─── Unit Cell ────────────────────────────────────────────────────────────────
function UnitCell({ unit, onClick }: { unit: Unit; onClick: () => void }) {
  const cfg = STATUS_CFG[unit.status];
  return (
    <button
      type="button"
      onClick={onClick}
      title={`№${unit.num} · ${unit.rooms}к · ${unit.area}м² · ${money(unit.price_kzt)}`}
      className={`relative flex flex-col items-center justify-center border rounded transition-all hover:scale-105 hover:shadow-md cursor-pointer ${cfg.bg} ${cfg.border} ${cfg.text}`}
      style={{ minWidth: 48, minHeight: 52, padding: "4px 2px" }}
    >
      <span className="text-[9px] font-mono leading-none opacity-70">№{unit.num}</span>
      <span className="text-[11px] font-semibold leading-none mt-0.5">{unit.rooms}к</span>
      <span className="text-[9px] leading-none opacity-80">{unit.area}м²</span>
      {unit.status === "sold" && <span className="absolute top-0.5 right-0.5 text-[7px]">✓</span>}
      {unit.status === "reserved" && <span className="absolute top-0.5 right-0.5 text-[7px]">⏱</span>}
    </button>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────
export function CrmChessView({ locale }: { locale: Locale }) {
  const isKk = locale === "kk";
  const [selectedBuilding, setSelectedBuilding] = useState("b1");
  const [filterStatus, setFilterStatus] = useState<UnitStatus | "all">("all");
  const [filterRooms, setFilterRooms] = useState<number | "all">("all");
  const [selectedUnit, setSelectedUnit] = useState<Unit | null>(null);
  const [viewMode, setViewMode] = useState<"chess" | "plan">("chess");

  const building = BUILDINGS.find((b) => b.id === selectedBuilding)!;

  const bUnitsAll = useMemo(() => ALL_UNITS.filter((u) => u.id.startsWith(selectedBuilding)), [selectedBuilding]);

  const filteredUnits = useMemo(() => {
    return bUnitsAll.filter((u) => {
      const sMatch = filterStatus === "all" || u.status === filterStatus;
      const rMatch = filterRooms === "all" || u.rooms === filterRooms;
      return sMatch && rMatch;
    });
  }, [bUnitsAll, filterStatus, filterRooms]);

  const stats = useMemo(() => {
    const total = bUnitsAll.length;
    const byStatus = Object.fromEntries(
      (Object.keys(STATUS_CFG) as UnitStatus[]).map((s) => [s, bUnitsAll.filter((u) => u.status === s).length])
    ) as Record<UnitStatus, number>;
    const revenue = bUnitsAll.filter((u) => u.status === "sold").reduce((a, u) => a + u.price_kzt, 0);
    const potential = bUnitsAll.filter((u) => u.status === "free").reduce((a, u) => a + u.price_kzt, 0);
    return { total, byStatus, revenue, potential };
  }, [bUnitsAll]);

  function getGrid(section: number) {
    const floors: number[] = [];
    for (let f = building.floors; f >= 1; f--) floors.push(f);
    return floors.map((f) => ({
      floor: f,
      units: filteredUnits.filter((u) => u.section === section && u.floor === f),
    }));
  }

  async function exportUnitsToExcel() {
    try {
      const XLSX = await import("xlsx");
      const wb = XLSX.utils.book_new();

      const data = [
        ["демо / иллюстративная модель"],
        ["ШАХМАТКА КВАРТИР И ПОМЕЩЕНИЙ · ЖК БЕСАГАШ РЕЗИДЕНС"],
        [`Корпус: ${building.name}`, `Секций: ${building.sections}`, `Этажей: ${building.floors}`],
        [],
        [
          "№ Квартиры",
          "Корпус",
          "Секция",
          "Этаж",
          "Комнат",
          "Площадь (м²)",
          "Цена (₸)",
          "Цена за м² (₸)",
          "Статус",
          "Клиент",
          "Ориентация",
        ],
        ...bUnitsAll.map((u) => [
          `№${u.num}`,
          building.name,
          u.section,
          u.floor,
          u.rooms,
          u.area,
          u.price_kzt,
          Math.round(u.price_kzt / u.area),
          STATUS_CFG[u.status]?.label || u.status,
          u.client || "—",
          u.facing,
        ]),
      ];

      const ws = XLSX.utils.aoa_to_sheet(data);
      ws["!cols"] = [
        { wch: 14 },
        { wch: 14 },
        { wch: 10 },
        { wch: 8 },
        { wch: 10 },
        { wch: 14 },
        { wch: 16 },
        { wch: 16 },
        { wch: 14 },
        { wch: 18 },
        { wch: 14 },
      ];

      XLSX.utils.book_append_sheet(wb, ws, building.name);
      const filename = `Shahmatka_${building.name.replace(/\s+/g, "_")}.xlsx`;
      const saved = await saveBlobDownload(filename, bytesToBlob(XLSX.write(wb, { bookType: "xlsx", type: "array" }), XLSX_MIME));
      if (!saved) XLSX.writeFile(wb, filename);
    } catch (e: any) {
      alert("Ошибка экспорта: " + e.message);
    }
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-white rounded-xl border border-ink/10 p-4 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-serif text-lg font-bold text-ink">
              {isKk ? "Шахматка / Генплан" : "🏗 Шахматка / Генплан"}
            </h3>
            <p className="mt-1 inline-flex rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-900">
              демо / иллюстративная модель
            </p>
            <p className="text-xs text-ink/50 mt-0.5">
              {isKk ? "Қабат бойынша жоспар. Деректер нақты объект емес." : "Интерактивная сетка квартир по этажам. Цены и статусы не относятся к реальному объекту."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={exportUnitsToExcel}
              className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-xs"
            >
              <span>📊</span>
              <span>В Excel (.xlsx)</span>
            </button>
            <div className="flex items-center gap-1 bg-paper border border-ink/10 rounded-lg p-1 text-xs">
              <button type="button" onClick={() => setViewMode("chess")}
                className={`px-3 py-1.5 rounded-md font-medium transition-colors ${viewMode === "chess" ? "bg-white text-pine font-semibold shadow-xs" : "text-ink/55 hover:text-ink"}`}>
                📊 Шахматка
              </button>
              <button type="button" onClick={() => setViewMode("plan")}
                className={`px-3 py-1.5 rounded-md font-medium transition-colors ${viewMode === "plan" ? "bg-white text-pine font-semibold shadow-xs" : "text-ink/55 hover:text-ink"}`}>
                📐 Генплан
              </button>
            </div>
          </div>
        </div>
        <div className="flex gap-2 mt-3 pt-3 border-t border-ink/10 overflow-x-auto">
          {BUILDINGS.map((b) => (
            <button key={b.id} type="button"
              onClick={() => { setSelectedBuilding(b.id); setSelectedUnit(null); }}
              className={`px-4 py-1.5 rounded-lg text-xs font-semibold border transition-all whitespace-nowrap ${
                selectedBuilding === b.id ? "bg-pine text-white border-pine shadow-xs" : "border-ink/15 text-ink/65 hover:bg-ink/5"
              }`}>
              {b.name}
            </button>
          ))}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
        {(Object.entries(STATUS_CFG) as [UnitStatus, typeof STATUS_CFG[UnitStatus]][]).map(([st, cfg]) => (
          <button key={st} type="button"
            onClick={() => setFilterStatus(filterStatus === st ? "all" : st)}
            className={`border rounded-xl p-3 text-left transition-all ${cfg.bg} ${cfg.border} ${filterStatus === st ? "ring-2 ring-pine shadow-md" : "hover:shadow-sm"}`}>
            <div className="flex items-center gap-1.5 mb-1">
              <span className={`w-2 h-2 rounded-full ${cfg.dot}`} />
              <span className={`text-[10px] font-semibold uppercase tracking-wide ${cfg.text}`}>{cfg.label}</span>
            </div>
            <p className={`text-xl font-bold ${cfg.text}`}>{stats.byStatus[st] ?? 0}</p>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-white border border-ink/10 rounded-xl p-3">
          <p className="text-[10px] text-ink/45 uppercase tracking-wider">Всего</p>
          <p className="text-2xl font-bold text-ink mt-0.5">{stats.total}</p>
        </div>
        <div className="bg-white border border-ink/10 rounded-xl p-3">
          <p className="text-[10px] text-ink/45 uppercase tracking-wider">Продано</p>
          <p className="text-2xl font-bold text-emerald-700 mt-0.5">{stats.byStatus.sold}</p>
        </div>
        <div className="bg-white border border-ink/10 rounded-xl p-3">
          <p className="text-[10px] text-ink/45 uppercase tracking-wider">Выручка</p>
          <p className="text-base font-bold text-emerald-700 mt-0.5">{money(stats.revenue)}</p>
        </div>
        <div className="bg-white border border-ink/10 rounded-xl p-3">
          <p className="text-[10px] text-ink/45 uppercase tracking-wider">Потенциал</p>
          <p className="text-base font-bold text-ink mt-0.5">{money(stats.potential)}</p>
        </div>
      </div>

      {/* Генплан */}
      {viewMode === "plan" && (
        <SitePlan selectedBuilding={selectedBuilding} onSelect={(id) => { setSelectedBuilding(id); setViewMode("chess"); }} />
      )}

      {/* Шахматка */}
      {viewMode === "chess" && (
        <div className="bg-white border border-ink/10 rounded-xl overflow-hidden">
          {/* Filters */}
          <div className="flex flex-wrap items-center gap-3 px-4 py-3 border-b border-ink/10 bg-paper/50">
            <span className="text-xs font-semibold text-ink/50 uppercase tracking-wider">Фильтр:</span>
            <div className="flex gap-1.5 flex-wrap">
              {[1, 2, 3, 4].map((r) => (
                <button key={r} type="button"
                  onClick={() => setFilterRooms(filterRooms === r ? "all" : r)}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium border transition-all ${
                    filterRooms === r ? "bg-pine text-white border-pine" : "border-ink/15 text-ink/65 hover:bg-ink/5"
                  }`}>
                  {r}к
                </button>
              ))}
              {(filterStatus !== "all" || filterRooms !== "all") && (
                <button type="button"
                  onClick={() => { setFilterStatus("all"); setFilterRooms("all"); }}
                  className="px-2.5 py-1 rounded-md text-xs text-clay border border-clay/30 hover:bg-clay/5">
                  ✕ Сброс
                </button>
              )}
            </div>
            <span className="ml-auto text-xs text-ink/45">{filteredUnits.length} / {bUnitsAll.length} ед.</span>
          </div>

          {/* Grid */}
          <div className="overflow-x-auto p-4">
            <div className="space-y-6">
              {Array.from({ length: building.sections }, (_, si) => si + 1).map((section) => (
                <div key={section}>
                  <p className="text-xs font-semibold text-ink/50 uppercase tracking-wider mb-2">Секция {section}</p>
                  <div className="border border-ink/10 rounded-lg overflow-hidden">
                    <div className="flex bg-ink/5 border-b border-ink/10">
                      <div className="flex items-center justify-center border-r border-ink/10 text-[10px] font-semibold text-ink/50 uppercase flex-shrink-0"
                        style={{ minWidth: 48, padding: "4px 2px" }}>Эт.</div>
                      {Array.from({ length: building.units_per_floor }, (_, i) => i + 1).map((u) => (
                        <div key={u} className="flex-1 flex items-center justify-center border-r border-ink/10 text-[10px] text-ink/40 font-medium"
                          style={{ minWidth: 48, padding: "4px 2px" }}>№{u}</div>
                      ))}
                    </div>
                    {getGrid(section).map(({ floor, units }) => (
                      <div key={floor} className="flex border-b border-ink/8 last:border-b-0 hover:bg-ink/2">
                        <div className="flex items-center justify-center border-r border-ink/10 bg-ink/3 text-[10px] font-bold text-ink/60 flex-shrink-0"
                          style={{ minWidth: 48 }}>{floor}</div>
                        <div className="flex gap-1 p-1 flex-1 flex-wrap">
                          {units.length > 0 ? (
                            units.map((unit) => (
                              <UnitCell key={unit.id} unit={unit} onClick={() => setSelectedUnit(unit)} />
                            ))
                          ) : (
                            <span className="text-[10px] text-ink/30 italic px-2 py-1">— нет совпадений</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Legend */}
          <div className="flex flex-wrap gap-3 px-4 py-3 border-t border-ink/10 bg-paper/30">
            {(Object.entries(STATUS_CFG) as [UnitStatus, typeof STATUS_CFG[UnitStatus]][]).map(([st, cfg]) => (
              <div key={st} className="flex items-center gap-1.5">
                <span className={`w-3 h-3 rounded border ${cfg.bg} ${cfg.border}`} />
                <span className="text-[10px] text-ink/55">{cfg.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Unit Drawer */}
      {selectedUnit && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-ink/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl border border-ink/15 overflow-hidden">
            <div className={`px-6 py-4 border-b border-ink/10 ${STATUS_CFG[selectedUnit.status].bg}`}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${STATUS_CFG[selectedUnit.status].text} border ${STATUS_CFG[selectedUnit.status].border}`}>
                      {STATUS_CFG[selectedUnit.status].label}
                    </span>
                    <span className="text-xs text-ink/50">ориентация: {selectedUnit.facing}</span>
                  </div>
                  <h3 className="font-serif text-xl font-bold text-ink mt-1">Квартира №{selectedUnit.num}</h3>
                  <p className="text-sm text-ink/60">{selectedUnit.rooms}-комнатная · {selectedUnit.area} м²</p>
                </div>
                <button type="button" onClick={() => setSelectedUnit(null)} className="text-ink/40 hover:text-ink text-xl leading-none mt-1">✕</button>
              </div>
            </div>
            <div className="px-6 py-4 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-paper rounded-xl p-3">
                  <p className="text-[10px] text-ink/45 uppercase tracking-wider">Площадь</p>
                  <p className="text-lg font-bold text-ink">{selectedUnit.area} м²</p>
                </div>
                <div className="bg-paper rounded-xl p-3">
                  <p className="text-[10px] text-ink/45 uppercase tracking-wider">Комнаты</p>
                  <p className="text-lg font-bold text-ink">{selectedUnit.rooms}к</p>
                </div>
                <div className="bg-paper rounded-xl p-3">
                  <p className="text-[10px] text-ink/45 uppercase tracking-wider">Этаж</p>
                  <p className="text-lg font-bold text-ink">{selectedUnit.floor}</p>
                </div>
                <div className="bg-paper rounded-xl p-3">
                  <p className="text-[10px] text-ink/45 uppercase tracking-wider">Секция</p>
                  <p className="text-lg font-bold text-ink">{selectedUnit.section}</p>
                </div>
              </div>
              <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
                <p className="text-[10px] text-emerald-600 uppercase tracking-wider font-semibold">Стоимость</p>
                <p className="text-2xl font-bold text-emerald-800">{money(selectedUnit.price_kzt)}</p>
                <p className="text-xs text-emerald-600 mt-0.5">{Math.round(selectedUnit.price_kzt / selectedUnit.area).toLocaleString()} тг/м²</p>
              </div>
              {selectedUnit.client && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-3">
                  <p className="text-[10px] text-amber-600 uppercase tracking-wider font-semibold mb-1">Клиент</p>
                  <p className="text-sm font-semibold text-amber-800">{selectedUnit.client}</p>
                </div>
              )}
              <div className="flex gap-2 pt-2">
                {selectedUnit.status === "free" && (
                  <>
                    <button type="button" className="flex-1 py-2.5 bg-pine text-white text-sm font-semibold rounded-xl hover:bg-pine/90 shadow-xs" onClick={() => setSelectedUnit(null)}>
                      Создать сделку
                    </button>
                    <button type="button" className="flex-1 py-2.5 bg-amber-500 text-white text-sm font-semibold rounded-xl hover:bg-amber-600 shadow-xs" onClick={() => setSelectedUnit(null)}>
                      Забронировать
                    </button>
                  </>
                )}
                {selectedUnit.status === "reserved" && (
                  <button type="button" className="flex-1 py-2.5 bg-pine text-white text-sm font-semibold rounded-xl hover:bg-pine/90 shadow-xs" onClick={() => setSelectedUnit(null)}>
                    Оформить продажу
                  </button>
                )}
                <button type="button" onClick={() => setSelectedUnit(null)} className="px-4 py-2.5 border border-ink/15 text-sm rounded-xl hover:bg-ink/5">
                  Закрыть
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
