"use client";

import { useEffect, useState } from "react";

export function useDebounced<T>(value: T, waitMs = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), waitMs);
    return () => window.clearTimeout(timer);
  }, [value, waitMs]);
  return debounced;
}
