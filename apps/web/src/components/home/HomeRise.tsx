"use client";

import { useLayoutEffect } from "react";

export function HomeRise() {
  useLayoutEffect(() => {
    const root = document.documentElement;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const nodes = Array.from(document.querySelectorAll<HTMLElement>(".home-rise"));
    root.classList.add("js-rise");
    const seen = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.classList.add("is-in");
          seen.unobserve(entry.target);
        }
      },
      { threshold: 0.14, rootMargin: "0px 0px -6% 0px" },
    );
    for (const node of nodes) seen.observe(node);
    return () => {
      seen.disconnect();
      root.classList.remove("js-rise");
      for (const node of nodes) node.classList.remove("is-in");
    };
  }, []);
  return null;
}
