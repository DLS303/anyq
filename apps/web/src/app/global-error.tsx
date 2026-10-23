"use client";

const copy = {
  ru: {
    errorTitle: "Страница не открылась",
    errorBody: "Повторите попытку. Если ошибка останется, обновите страницу.",
    retry: "Повторить",
  },
  kk: {
    errorTitle: "Бет ашылмады",
    errorBody: "Қайталап көріңіз. Қате қалса, бетті жаңартыңыз.",
    retry: "Қайталау",
  },
} as const;

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const locale = typeof window !== "undefined" && window.location.pathname.startsWith("/kk") ? "kk" : "ru";
  const m = copy[locale];
  return (
    <html lang={locale}>
      <body style={{ margin: 0, background: "#f8fafc", color: "#0f172a", fontFamily: "system-ui, sans-serif" }}>
        <main
          role="alert"
          style={{
            maxWidth: 480,
            margin: "0 auto",
            padding: "4rem 1rem",
            textAlign: "center",
          }}
        >
          <h1 style={{ fontSize: "1.5rem", fontWeight: 560 }}>{m.errorTitle}</h1>
          <p style={{ marginTop: "0.75rem", fontSize: "0.95rem", color: "#334155" }}>{m.errorBody}</p>
          <button
            type="button"
            onClick={() => reset()}
            style={{
              marginTop: "1.5rem",
              minHeight: 48,
              border: 0,
              borderRadius: 999,
              background: "#0f2942",
              color: "#f8fafc",
              padding: "0.75rem 1.25rem",
              font: "inherit",
            }}
          >
            {m.retry}
          </button>
        </main>
      </body>
    </html>
  );
}
