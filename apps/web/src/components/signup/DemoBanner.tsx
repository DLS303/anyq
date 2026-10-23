import { DEMO_BANNER_TEXT } from "@/lib/signupContact";

export function DemoBanner({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <p className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-950">
      {DEMO_BANNER_TEXT}
    </p>
  );
}
