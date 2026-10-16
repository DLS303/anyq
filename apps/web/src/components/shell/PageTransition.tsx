"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, type ReactNode } from "react";

function isHome(pathname: string) {
  return /^\/(ru|kk)\/?$/.test(pathname);
}

export function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const pageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = (event.target as Element | null)?.closest?.("a");
      if (!anchor || anchor.target === "_blank" || anchor.hasAttribute("download")) return;
      const href = anchor.getAttribute("href");
      if (!href || href.startsWith("#")) return;
      const url = new URL(href, window.location.href);
      if (url.origin !== window.location.origin) return;
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      const start = document.startViewTransition?.bind(document);
      const page = pageRef.current;
      if (!start || !page) return;

      event.preventDefault();
      page.classList.add("is-vt");
      const next = `${url.pathname}${url.search}${url.hash}`;
      const transition = start(async () => {
        await new Promise<void>((resolve) => {
          const timeout = window.setTimeout(() => {
            observer.disconnect();
            resolve();
          }, 3500);
          const observer = new MutationObserver(() => {
            if (window.location.pathname !== url.pathname) return;
            window.clearTimeout(timeout);
            observer.disconnect();
            requestAnimationFrame(() => resolve());
          });
          observer.observe(document.body, { childList: true, subtree: true });
          router.push(next);
        });
      });
      transition.finished.finally(() => {
        pageRef.current?.classList.remove("is-vt");
      });
    }

    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [router]);

  return (
    <div ref={pageRef} key={pathname} className={isHome(pathname) ? "anyq-page" : "anyq-page luxury-page-enter"}>
      {children}
    </div>
  );
}
