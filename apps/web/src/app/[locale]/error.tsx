"use client";

import { useMessages } from "@/lib/i18n";

export default function LocaleError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const m = useMessages();
  return (
    <main role="alert" className="mx-auto max-w-lg px-3 py-16 text-center">
      <h1 className="text-2xl font-medium">{m.errorTitle}</h1>
      <p className="mt-3 text-sm text-ink/70">{m.errorBody}</p>
      <button type="button" className="btn-ice mt-6" onClick={() => reset()}>
        {m.retry}
      </button>
    </main>
  );
}
