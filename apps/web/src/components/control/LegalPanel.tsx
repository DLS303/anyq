"use client";

import Link from "next/link";
import { useState } from "react";
import { ChevronDown, Scale, ShieldCheck } from "lucide-react";
import { fetchSpecialists } from "@/lib/api";
import { ErrorRetry, useAsync } from "@/lib/useAsync";
import { t } from "@/i18n/messages";
import type { Locale } from "@/lib/types";

const QUESTIONS: { q: string; a: string }[] = [
  {
    q: "Что зафиксировать в договоре подряда до аванса",
    a: "Предмет, адрес объекта, срок и этапы, что входит в цену, порядок КС-2 и КС-3, удержание, гарантийный срок и кто сдаёт исполнительную документацию.",
  },
  {
    q: "Как проверить лицензию подрядчика",
    a: "До оплаты смотрите категорию и срок лицензии на генподряд или СМР. В карточке специалиста ANYQ это поле «Лицензия» и отметка проверки.",
  },
  {
    q: "Когда подписывать КС-2 и КС-3",
    a: "Объём закрывается актом по факту принятых работ. Счёт на этап идёт после акта, а не вместо него. Расхождение сметы и акта видно в разделе «Сметы».",
  },
  {
    q: "Что делать, если срок сорван",
    a: "Зафиксируйте дату в журнале площадки и в переписке сделки. Претензия ссылается на пункт срока договора и на последний принятый акт.",
  },
  {
    q: "Как проводить оплату по этапам",
    a: "Аванс, этап после акта, удержание до устранения замечаний. Счёт живёт в CRM, в воронке «Юр. оформление».",
  },
];

export function LegalPanel({ locale }: { locale: Locale }) {
  const m = t(locale);
  const [open, setOpen] = useState(0);
  const query = useAsync((signal) => fetchSpecialists({ category: "legal" }, signal), []);
  const people = query.data ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-slate-950">Юридические вопросы</h2>
        <p className="mt-1 max-w-xl text-sm text-slate-500">
          Короткий разбор до договора. Это ориентир по стройке, не юридическое заключение.
        </p>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        {QUESTIONS.map((item, index) => {
          const on = open === index;
          return (
            <div key={item.q} className="border-b border-slate-100 last:border-b-0">
              <button
                type="button"
                className="flex w-full items-center gap-3 px-4 py-3.5 text-left"
                aria-expanded={on}
                onClick={() => setOpen(on ? -1 : index)}
              >
                <Scale className="h-4 w-4 shrink-0 text-[#2F5B8A]" />
                <span className="flex-1 text-sm font-medium text-slate-900">{item.q}</span>
                <ChevronDown className={`h-4 w-4 text-slate-400 transition-transform ${on ? "rotate-180" : ""}`} />
              </button>
              {on ? <p className="px-11 pb-4 text-sm leading-6 text-slate-600">{item.a}</p> : null}
            </div>
          );
        })}
      </div>

      <div>
        <h3 className="text-sm font-semibold text-slate-950">Юристы в реестре</h3>
        <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200 bg-white">
          {query.loading ? <p className="px-4 py-6 text-sm text-slate-500">{m.hubLoading}</p> : null}
          {query.status === "error" ? (
            <div className="p-4">
              <ErrorRetry message={m.listLoadError} retryLabel={m.retry} onRetry={query.reload} />
            </div>
          ) : null}
          {!query.loading && query.status !== "error" && people.length === 0 ? (
            <p className="px-4 py-6 text-sm text-slate-500">В реестре пока нет карточек с категорией «юрист».</p>
          ) : null}
          {query.status !== "error" && people.length > 0 ? (
            people.map((person) => (
              <Link
                key={person.id}
                href={`/${locale}/specialists/${person.slug}`}
                className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3.5 last:border-b-0 hover:bg-slate-50"
              >
                <span>
                  <span className="block text-sm font-medium text-slate-950">
                    {locale === "kk" ? person.company_kk : person.company_ru}
                  </span>
                  <span className="mt-0.5 block text-xs text-slate-500">
                    {person.city}
                    {person.license_verified ? ` · лицензия ${person.license_cat}` : ""}
                  </span>
                </span>
                {person.license_verified ? <ShieldCheck className="h-4 w-4 text-emerald-600" /> : null}
              </Link>
            ))
          ) : null}
        </div>
      </div>
    </div>
  );
}
