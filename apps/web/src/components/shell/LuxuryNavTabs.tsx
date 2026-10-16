"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { LucideIcon } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

// Whisper-quiet tactile synthesized micro-haptic sound
function playHapticSound() {
  if (typeof window === "undefined") return;
  try {
    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = "sine";
    // Gentle 1050Hz to 620Hz acoustic glass tap
    osc.frequency.setValueAtTime(1050, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(620, ctx.currentTime + 0.028);

    // Whisper volume (0.018) - purely subliminal luxury tactile feel
    gain.gain.setValueAtTime(0.018, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.028);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start();
    osc.stop(ctx.currentTime + 0.03);

    setTimeout(() => {
      ctx.close().catch(() => {});
    }, 100);
  } catch {
    // Audio context may be restricted by autoplay policy; silent fallback
  }
}

export function LuxuryNavTabs({ items }: { items: NavItem[] }) {
  const pathname = usePathname();
  const router = useRouter();
  const [, startTransition] = useTransition();

  const navRef = useRef<HTMLElement>(null);
  const itemRefs = useRef<(HTMLAnchorElement | null)[]>([]);

  // Active pill bounds (offsetLeft & offsetWidth)
  const [activeRect, setActiveRect] = useState<{ left: number; width: number } | null>(null);

  // Hover spotlight aura bounds
  const [hoverRect, setHoverRect] = useState<{ left: number; width: number } | null>(null);

  // Active pressed item index for micro-scale spring
  const [pressedIndex, setPressedIndex] = useState<number | null>(null);

  // Update active pill position based on current pathname
  useEffect(() => {
    const activeIndex = items.findIndex((it) => {
      return pathname === it.href || pathname.startsWith(it.href + "/");
    });

    if (activeIndex !== -1 && itemRefs.current[activeIndex] && navRef.current) {
      const el = itemRefs.current[activeIndex];
      const navEl = navRef.current;
      const elRect = el.getBoundingClientRect();
      const navRect = navEl.getBoundingClientRect();
      setActiveRect({
        left: elRect.left - navRect.left,
        width: elRect.width,
      });
    } else {
      setActiveRect(null);
    }
  }, [pathname, items]);

  // Recalculate on window resize
  useEffect(() => {
    function handleResize() {
      const activeIndex = items.findIndex(
        (it) => pathname === it.href || pathname.startsWith(it.href + "/")
      );
      if (activeIndex !== -1 && itemRefs.current[activeIndex] && navRef.current) {
        const el = itemRefs.current[activeIndex];
        const navEl = navRef.current;
        const elRect = el.getBoundingClientRect();
        const navRect = navEl.getBoundingClientRect();
        setActiveRect({
          left: elRect.left - navRect.left,
          width: elRect.width,
        });
      }
    }
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [pathname, items]);

  // Smooth luxury navigation with View Transitions API support
  const handleTabClick = (e: React.MouseEvent<HTMLAnchorElement>, href: string, index: number) => {
    playHapticSound();
    setPressedIndex(index);
    setTimeout(() => setPressedIndex(null), 200);

    if (pathname === href || e.defaultPrevented) return;

    if (typeof document !== "undefined" && "startViewTransition" in document) {
      e.preventDefault();
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (document as any).startViewTransition(() => {
        startTransition(() => {
          router.push(href);
        });
      });
    }
  };

  return (
    <nav
      ref={navRef}
      onMouseLeave={() => setHoverRect(null)}
      className="relative hidden lg:flex items-center gap-0.5 text-[13px] font-medium ml-1 p-1 rounded-full bg-slate-900/[0.03] border border-slate-900/[0.04] backdrop-blur-xs select-none"
    >
      {/* 1. Floating Hover Spotlight Aura (Follows cursor) */}
      {hoverRect && (
        <div
          aria-hidden="true"
          className="absolute top-1 bottom-1 rounded-full bg-white/60 pointer-events-none transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]"
          style={{
            transform: `translateX(${hoverRect.left}px)`,
            width: `${hoverRect.width}px`,
          }}
        />
      )}

      {/* 2. Primary Gliding Glass Capsule (Active tab indicator) */}
      {activeRect && (
        <div
          aria-hidden="true"
          className="absolute top-1 bottom-1 rounded-full pointer-events-none transition-all duration-350 ease-[cubic-bezier(0.16,1,0.3,1)] z-0"
          style={{
            transform: `translateX(${activeRect.left}px)`,
            width: `${activeRect.width}px`,
            background: "rgba(255, 255, 255, 0.98)",
            boxShadow:
              "0 4px 16px -2px rgba(15, 23, 42, 0.08), 0 1px 3px rgba(15, 23, 42, 0.04), inset 0 1px 0 rgba(255, 255, 255, 1), inset 0 -1px 1px rgba(0, 0, 0, 0.02)",
            border: "1px solid rgba(226, 232, 240, 0.95)",
            backdropFilter: "blur(16px)",
          }}
        >
          {/* Subtle top specular glass reflection */}
          <div className="absolute inset-x-2 top-0 h-[1px] bg-gradient-to-r from-transparent via-white to-transparent opacity-90" />
        </div>
      )}

      {/* 3. Navigation Links */}
      {items.map((item, index) => {
        const active = pathname === item.href || pathname.startsWith(item.href + "/");
        const isPressed = pressedIndex === index;

        return (
          <Link
            key={item.href}
            ref={(el) => {
              itemRefs.current[index] = el;
            }}
            href={item.href}
            onClick={(e) => handleTabClick(e, item.href, index)}
            onMouseEnter={() => {
              const el = itemRefs.current[index];
              const navEl = navRef.current;
              if (el && navEl) {
                const elRect = el.getBoundingClientRect();
                const navRect = navEl.getBoundingClientRect();
                setHoverRect({
                  left: elRect.left - navRect.left,
                  width: elRect.width,
                });
              }
            }}
            className={`relative z-10 rounded-full px-3.5 py-1.5 transition-all duration-200 flex items-center gap-1.5 cursor-pointer ${
              isPressed ? "scale-95" : "hover:scale-[1.01]"
            } ${
              active
                ? "text-[#0f2942] font-semibold"
                : "text-slate-600 hover:text-[#0f2942]"
            }`}
          >
            {/* Active breathing clarity jewel dot */}
            {active && (
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#2F5B8A] opacity-60" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-[#2F5B8A]" />
              </span>
            )}
            <span className="tracking-tight">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
