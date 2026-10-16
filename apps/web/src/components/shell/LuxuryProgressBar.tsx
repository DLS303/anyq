"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

export function LuxuryProgressBar() {
  const pathname = usePathname();
  const [active, setActive] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    // When pathname changes, fire a high-speed luminous laser across the top
    setActive(true);
    setProgress(15);

    const t1 = setTimeout(() => setProgress(65), 60);
    const t2 = setTimeout(() => setProgress(90), 180);
    const t3 = setTimeout(() => {
      setProgress(100);
      const t4 = setTimeout(() => {
        setActive(false);
        setProgress(0);
      }, 240);
      return () => clearTimeout(t4);
    }, 280);

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
    };
  }, [pathname]);

  if (!active && progress === 0) return null;

  return (
    <div
      aria-hidden="true"
      className="fixed top-0 left-0 right-0 z-[100] h-[2.5px] pointer-events-none overflow-hidden"
    >
      <div
        className="h-full transition-all ease-out relative"
        style={{
          width: `${progress}%`,
          transitionDuration: progress === 100 ? "200ms" : "280ms",
          background:
            "linear-gradient(90deg, #2F5B8A 0%, #3E7A62 45%, #D4AF37 85%, #6A93C2 100%)",
          boxShadow:
            "0 0 10px rgba(47, 91, 138, 0.8), 0 0 20px rgba(62, 122, 98, 0.6), 0 0 30px rgba(212, 175, 55, 0.4)",
        }}
      >
        {/* Leading glowing spark */}
        <div className="absolute right-0 top-1/2 -translate-y-1/2 w-8 h-3 -mr-2 rounded-full bg-white blur-[2px] opacity-90 animate-pulse" />
      </div>
    </div>
  );
}
