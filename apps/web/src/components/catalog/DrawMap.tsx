"use client";

import { CircleMarker, MapContainer, Polygon, TileLayer, useMapEvents } from "react-leaflet";
import "leaflet/dist/leaflet.css";

const ALMATY: [number, number] = [43.24, 76.92];

function Clicker({ onAdd }: { onAdd: (pt: [number, number]) => void }) {
  useMapEvents({
    click(e) {
      onAdd([e.latlng.lat, e.latlng.lng]);
    },
  });
  return null;
}

export default function DrawMap({
  points,
  onAdd,
}: {
  points: [number, number][];
  onAdd: (pt: [number, number]) => void;
}) {
  return (
    <MapContainer center={ALMATY} zoom={11} className="h-full w-full min-h-[360px]" scrollWheelZoom>
      <TileLayer attribution="&copy; OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <Clicker onAdd={onAdd} />
      {points.length >= 3 ? (
        <Polygon positions={points} pathOptions={{ color: "#1d3a30", fillColor: "#c4a574", fillOpacity: 0.35 }} />
      ) : null}
      {points.map((pt, i) => (
        <CircleMarker key={`${pt[0]}-${pt[1]}-${i}`} center={pt} radius={6} pathOptions={{ color: "#9a4f34" }} />
      ))}
    </MapContainer>
  );
}
