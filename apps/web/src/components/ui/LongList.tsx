"use client";

import { useEffect, useRef, useState } from "react";

export function LongList<T>({
  items,
  pageSize = 24,
  getKey,
  render,
}: {
  items: T[];
  pageSize?: number;
  getKey: (item: T) => string;
  render: (item: T) => React.ReactNode;
}) {
  const [count, setCount] = useState(pageSize);
  const sentinel = useRef<HTMLDivElement>(null);
  const itemKey = items.map(getKey).join("\n");

  useEffect(() => {
    setCount(pageSize);
  }, [itemKey, pageSize]);

  useEffect(() => {
    const node = sentinel.current;
    if (!node || count >= items.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setCount((value) => Math.min(items.length, value + pageSize));
        }
      },
      { rootMargin: "600px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [count, items.length, pageSize]);

  return (
    <>
      {items.slice(0, count).map((item) => (
        <div key={getKey(item)} className="long-row">
          {render(item)}
        </div>
      ))}
      {count < items.length ? <div ref={sentinel} className="h-8" aria-hidden /> : null}
    </>
  );
}
