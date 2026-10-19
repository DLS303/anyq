"use client";

import { useState } from "react";
import { useAsync } from "@/lib/useAsync";

export const PAGE_SIZE = 24;

export function usePaged<T>(items: readonly T[], resetKey: string, pageSize = PAGE_SIZE) {
  const [key, setKey] = useState(resetKey);
  const [page, setPage] = useState(0);
  if (key !== resetKey) {
    setKey(resetKey);
    setPage(0);
  }
  const pages = Math.max(1, Math.ceil(items.length / pageSize));
  const current = Math.min(page, pages - 1);
  const start = current * pageSize;
  return {
    page: current,
    pages,
    total: items.length,
    slice: items.slice(start, start + pageSize),
    setPage,
  };
}

export function useServerPaged<T>(
  resetKey: string,
  loader: (page: number, signal: AbortSignal) => Promise<{ items: T[]; total: number }>,
  pageSize = PAGE_SIZE,
) {
  const [state, setState] = useState({ key: resetKey, page: 0 });
  const page = state.key === resetKey ? state.page : 0;
  if (state.key !== resetKey) {
    setState({ key: resetKey, page: 0 });
  }
  const query = useAsync((signal) => loader(page, signal), [resetKey, page, pageSize]);
  const total = query.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return {
    page,
    pages,
    total,
    slice: query.data?.items ?? [],
    setPage: (next: number) => setState({ key: resetKey, page: next }),
    loading: query.loading,
    status: query.status,
    reload: query.reload,
  };
}

export function PageNav({
  page,
  pages,
  status,
  prevLabel,
  nextLabel,
  onPage,
}: {
  page: number;
  pages: number;
  status: string;
  prevLabel: string;
  nextLabel: string;
  onPage: (page: number) => void;
}) {
  if (pages <= 1) return null;
  return (
    <nav className="mt-4 flex flex-wrap items-center justify-between gap-2" aria-label={status}>
      <button
        type="button"
        className="inline-flex min-h-11 items-center rounded-full border border-ink/15 px-4 text-sm disabled:opacity-40"
        disabled={page <= 0}
        onClick={() => onPage(page - 1)}
      >
        {prevLabel}
      </button>
      <p className="text-xs text-ink/55">{status}</p>
      <button
        type="button"
        className="inline-flex min-h-11 items-center rounded-full border border-ink/15 px-4 text-sm disabled:opacity-40"
        disabled={page >= pages - 1}
        onClick={() => onPage(page + 1)}
      >
        {nextLabel}
      </button>
    </nav>
  );
}
