"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { toast } from "@/lib/toast";

type Status = "loading" | "error" | "ready";

export function isMissing(error: unknown) {
  return error instanceof ApiError && (error.status === 404 || error.status === 403);
}

export function useAsync<T>(loader: () => Promise<T>, deps: readonly unknown[]) {
  const depKey = JSON.stringify(deps);
  const [epoch, setEpoch] = useState(depKey);
  const [status, setStatus] = useState<Status>("loading");
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const loaderRef = useRef(loader);
  const seq = useRef(0);
  loaderRef.current = loader;
  if (epoch !== depKey) {
    setEpoch(depKey);
    setData(null);
    setStatus("loading");
    setError(null);
  }

  const reload = useCallback(() => {
    const id = ++seq.current;
    const requestKey = depKey;
    setError(null);
    setStatus((prev) => (prev === "ready" ? prev : "loading"));
    loaderRef
      .current()
      .then((value) => {
        if (seq.current !== id || requestKey !== depKey) return;
        setData(value);
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (seq.current !== id || requestKey !== depKey) return;
        setError(err);
        setStatus("error");
      });
  }, [depKey]);

  useEffect(() => {
    reload();
  }, [reload]);

  return {
    status,
    data,
    error,
    reload,
    loading: status === "loading" && data === null,
  };
}

export function useGuardedSubmit(success: string, failure: string, onDone: () => void) {
  const lock = useRef(false);
  const [submitting, setSubmitting] = useState(false);
  const doneRef = useRef(onDone);
  const successRef = useRef(success);
  const failureRef = useRef(failure);
  doneRef.current = onDone;
  successRef.current = success;
  failureRef.current = failure;

  async function submit(task: (key: string) => Promise<HTMLFormElement | null | void>) {
    if (lock.current) return;
    lock.current = true;
    setSubmitting(true);
    const key = crypto.randomUUID();
    try {
      const form = await task(key);
      form?.reset();
      toast(successRef.current);
      doneRef.current();
    } catch (err) {
      toast(err instanceof Error ? err.message : failureRef.current);
    } finally {
      lock.current = false;
      setSubmitting(false);
    }
  }

  return { submitting, submit };
}

export function LoadingSkeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-busy="true" aria-label={label} className="grid gap-3">
      <div className="h-8 w-2/3 animate-pulse bg-ink/10" />
      <div className="h-24 animate-pulse bg-ink/10" />
      <div className="h-24 animate-pulse bg-ink/10" />
    </div>
  );
}

export function ErrorRetry({
  message,
  retryLabel,
  onRetry,
}: {
  message: string;
  retryLabel: string;
  onRetry: () => void;
}) {
  return (
    <div role="alert" className="border border-ink/10 bg-white/50 p-6 text-center">
      <p className="text-sm text-ink/70">{message}</p>
      <button
        type="button"
        className="mt-4 inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper"
        onClick={onRetry}
      >
        {retryLabel}
      </button>
    </div>
  );
}
