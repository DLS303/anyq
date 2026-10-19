import type { Metadata } from "next";
import { PhotoView } from "@/components/media/PhotoView";
import { t } from "@/i18n/messages";
import { apiFetch } from "@/lib/api";
import { roleLabel, weatherLabel } from "@/lib/report";
import type { Locale } from "@/lib/types";

export const dynamic = "force-dynamic";

type PublicDaily = {
  day: string;
  weather: string;
  temp_c: number;
  workers: number;
  notes: string;
  delays: string;
  delay_hours?: number;
  project_title: string;
  author_role: string;
  photos: { url: string }[];
};

async function loadReport(token: string): Promise<{ status: number; data: PublicDaily | null }> {
  try {
    const res = await apiFetch(`/v1/public/daily/${encodeURIComponent(token)}`, { auth: false });
    if (!res.ok) return { status: res.status, data: null };
    const json = (await res.json()) as { data?: PublicDaily };
    return { status: 200, data: json.data ?? null };
  } catch {
    return { status: 404, data: null };
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; token: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const m = t(locale === "kk" ? "kk" : "ru");
  return {
    title: m.reportPublicTitle,
    robots: { index: false, follow: false },
    referrer: "no-referrer",
  };
}

export default async function PublicDailyPage({
  params,
}: {
  params: Promise<{ locale: string; token: string }>;
}) {
  const { locale: rawLocale, token } = await params;
  const locale: Locale = rawLocale === "kk" ? "kk" : "ru";
  const m = t(locale);
  const { status, data } = await loadReport(token);
  if (!data) {
    return (
      <article className="mx-auto max-w-lg min-w-0 py-10 text-center">
        <h1 className="text-2xl font-medium">{m.reportPublicTitle}</h1>
        <p className="mt-3 text-sm text-ink/70">{status === 410 ? m.reportExpired : m.reportMissing}</p>
      </article>
    );
  }
  const author = roleLabel(data.author_role, m);
  return (
    <article className="mx-auto max-w-lg min-w-0">
      <p className="text-xs uppercase tracking-wider text-ink/45">{m.reportPublicTitle}</p>
      <h1 className="mt-1 text-2xl font-medium tracking-tight">{data.project_title}</h1>
      <p className="mt-2 text-sm text-ink/70">
        {data.day}
        {author ? ` · ${m.reportAuthor}: ${author}` : ""}
      </p>
      {data.photos.length ? (
        <div className="mt-4 grid gap-3">
          {data.photos.map((photo) => (
            <PhotoView
              key={photo.url}
              src={photo.url}
              alt={m.reportPhotoAlt}
              sizes="(max-width: 640px) 100vw, 32rem"
              className="max-h-[70vh] w-full bg-white object-contain"
            />
          ))}
        </div>
      ) : null}
      <dl className="mt-4 grid gap-3 text-sm">
        <div>
          <dt className="text-ink/45">{m.reportWeather}</dt>
          <dd>
            {weatherLabel(data.weather, m)} · {data.temp_c}°
          </dd>
        </div>
        <div>
          <dt className="text-ink/45">{m.reportWorkers}</dt>
          <dd>{data.workers}</dd>
        </div>
        {data.notes ? (
          <div>
            <dt className="text-ink/45">{m.reportNotes}</dt>
            <dd className="whitespace-pre-wrap">{data.notes}</dd>
          </div>
        ) : null}
        {data.delays || data.delay_hours ? (
          <div>
            <dt className="text-ink/45">{m.reportDelaysLabel}</dt>
            <dd className="whitespace-pre-wrap">
              {data.delays}
              {data.delay_hours ? ` · ${data.delay_hours} ${m.hubHours}` : ""}
            </dd>
          </div>
        ) : null}
      </dl>
    </article>
  );
}
