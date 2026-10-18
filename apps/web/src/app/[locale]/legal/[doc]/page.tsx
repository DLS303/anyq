import fs from "node:fs";
import path from "node:path";
import { notFound } from "next/navigation";
import { renderMarkdown } from "@/lib/markdown";
import type { Locale } from "@/lib/types";

const DOCS: Record<string, { file: string; title: string }> = {
  privacy: { file: "privacy.ru.md", title: "Политика конфиденциальности" },
  "pd-consent": { file: "pd-consent.ru.md", title: "Согласие на обработку персональных данных" },
};

export function generateStaticParams() {
  return Object.keys(DOCS).map((doc) => ({ doc }));
}

export default async function LegalDocPage({ params }: { params: Promise<{ locale: string; doc: string }> }) {
  const { locale: raw, doc } = await params;
  const locale = (raw === "kk" ? "kk" : "ru") as Locale;
  const spec = DOCS[doc];
  if (!spec) notFound();
  const file = path.join(process.cwd(), "content", "legal", spec.file);
  const source = fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
  const html = source ? renderMarkdown(source) : "";
  return (
    <article className="mx-auto max-w-3xl py-6 text-sm text-slate-700">
      <p className="text-xs uppercase tracking-wider text-slate-400">{locale === "kk" ? "Құжат" : "Документ"}</p>
      <h1 className="mt-2 text-2xl font-semibold text-slate-950">{spec.title}</h1>
      {html ? (
        <div className="mt-4" dangerouslySetInnerHTML={{ __html: html }} />
      ) : (
        <p className="mt-6">Документ готовится.</p>
      )}
    </article>
  );
}
