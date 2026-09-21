"use client";

import { CircleMarker, MapContainer, Polygon, Popup, TileLayer, useMapEvents } from "react-leaflet";
import type { Locale, Plot } from "@/lib/types";
import { money, titleOf } from "@/lib/format";
import Link from "next/link";
import "leaflet/dist/leaflet.css";

const ALMATY: [number, number] = [43.24, 76.92];

function Clicker({ onPick }: { onPick?: (pt: [number, number]) => void }) {
  useMapEvents({
    click(e) {
      onPick?.([e.latlng.lat, e.latlng.lng]);
    },
  });
  return null;
}

export default function PlotMap({
  plots,
  locale,
  onPick,
  pick,
}: {
  plots: Plot[];
  locale: Locale;
  onPick?: (pt: [number, number]) => void;
  pick?: [number, number] | null;
}) {
  return (
    <MapContainer center={ALMATY} zoom={10} className="h-full w-full min-h-[420px]" scrollWheelZoom>
      <TileLayer attribution="&copy; OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {onPick ? <Clicker onPick={onPick} /> : null}
      {pick ? <CircleMarker center={pick} radius={8} pathOptions={{ color: "#2F5B8A" }} /> : null}
      {plots.map((plot) => (
        <Polygon
          key={plot.id}
          positions={plot.polygon as [number, number][]}
          pathOptions={{
            color: "#2F5B8A",
            fillColor: plot.verified ? "#3E7A62" : "#B56A43",
            fillOpacity: 0.28,
            weight: 1.5,
          }}
        >
          <Popup>
            <div className="min-w-[160px]">
              <p className="font-medium">{titleOf(plot, locale)}</p>
              <p className="text-sm">{money(plot.price_kzt, locale)}</p>
              <Link href={`/${locale}/plots/${plot.slug}`} className="text-pine text-sm underline">
                паспорт
              </Link>
            </div>
          </Popup>
        </Polygon>
      ))}
    </MapContainer>
  );
}
