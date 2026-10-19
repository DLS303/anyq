"use client";

import { useState } from "react";
import { PageNav, usePaged } from "@/components/ui/PagedList";
import { useAuth } from "@/lib/auth";
import { createContact, fetchContacts } from "@/lib/api";
import { useDebounced } from "@/lib/useDebounced";
import { ErrorRetry, useAsync, useSubmitLock } from "@/lib/useAsync";
import { t } from "@/i18n/messages";
import { CONTACT_TYPE, money } from "@/lib/format";
import type { ContactType, CrmContact, Locale } from "@/lib/types";

export function CrmContactsView({ locale }: { locale: Locale }) {
  const { user } = useAuth();
  const m = t(locale);
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search, 300);
  const [typeFilter, setTypeFilter] = useState<string>("");
  const createLock = useSubmitLock();
  const contactsQuery = useAsync(
    (signal) =>
      user
        ? fetchContacts(user.email, { q: debouncedSearch || undefined, ctype: typeFilter || undefined }, signal)
        : Promise.resolve([] as CrmContact[]),
    [user?.email, typeFilter, debouncedSearch],
  );
  const contacts = contactsQuery.data ?? [];
  const paged = usePaged(contacts, `${typeFilter}:${debouncedSearch}`);
  const loading = contactsQuery.loading;
  const load = contactsQuery.reload;

  // New Contact Modal
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newCompany, setNewCompany] = useState("");
  const [newBinIin, setNewBinIin] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newCity, setNewCity] = useState("Алматы");
  const [newType, setNewType] = useState<ContactType>("client");
  const [newNotes, setNewNotes] = useState("");

  async function handleCreateSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!user || !newName.trim() || !newPhone.trim() || createLock.pending) {
      if (!newName.trim() || !newPhone.trim()) alert("Заполните имя и телефон");
      return;
    }
    await createLock.run(async () => {
    try {
      await createContact(user.email, {
        name: newName.trim(),
        company_name: newCompany.trim(),
        bin_iin: newBinIin.trim(),
        phone: newPhone.trim(),
        email: newEmail.trim(),
        city: newCity.trim(),
        contact_type: newType,
        notes: newNotes.trim(),
      });
      setIsCreating(false);
      setNewName("");
      setNewCompany("");
      setNewBinIin("");
      setNewPhone("");
      setNewEmail("");
      setNewNotes("");
      load();
      alert("Контакт успешно добавлен в базу CRM!");
    } catch (err) {
      alert((err as Error).message);
    }
    });
  }

  return (
    <div className="space-y-4">
      {/* Search and Filter Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-white p-4 rounded-xl border border-ink/10 shadow-xs">
        <div className="flex flex-wrap items-center gap-2 flex-1 max-w-xl">
          <div className="relative min-w-0 flex-1 basis-full sm:basis-auto sm:min-w-[12rem]">
            <input
              type="text"
              placeholder="Поиск по имени, БИН/ИИН, телефону..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && load()}
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-ink/15 bg-white focus:outline-none focus:border-pine"
            />
            <span className="absolute left-2.5 top-2 text-xs text-ink/40">🔍</span>
          </div>
          <button
            type="button"
            onClick={load}
            className="px-3 py-1.5 bg-paper border border-ink/15 rounded-lg text-xs hover:bg-ink/5"
          >
            Найти
          </button>
        </div>

        <button
          type="button"
          onClick={() => setIsCreating(true)}
          className="px-4 py-1.5 bg-pine text-white text-xs font-semibold rounded-lg hover:bg-pine/90 transition-colors shadow-xs flex items-center gap-1.5"
        >
          <span>+</span> Новый контакт / контрагент
        </button>
      </div>

      {/* Category Filter Pills */}
      <div className="flex flex-wrap items-center gap-1.5">
        {[
          { id: "", label: "Все контрагенты" },
          { id: "client", label: "Клиенты" },
          { id: "contractor", label: "Подрядчики / Проектировщики" },
          { id: "supplier", label: "Поставщики материалов" },
          { id: "investor", label: "Инвесторы" },
        ].map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setTypeFilter(f.id)}
            className={`px-3 py-1 text-xs rounded-full border transition-all ${
              typeFilter === f.id
                ? "bg-pine text-white border-pine font-medium shadow-xs"
                : "bg-white border-ink/15 text-ink/70 hover:bg-ink/5"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Contacts Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {contactsQuery.status === "error" && !contactsQuery.data ? (
          <div className="col-span-full">
            <ErrorRetry message={m.listLoadError} retryLabel={m.hubRetry} onRetry={load} />
          </div>
        ) : loading ? (
          <div className="col-span-full py-12 text-center text-xs text-ink/40">
            Загрузка контактов...
          </div>
        ) : contacts.length === 0 ? (
          <div className="col-span-full py-12 text-center text-xs text-ink/40 italic">
            Контактов не найдено
          </div>
        ) : (
          paged.slice.map((c) => (
            <div
              key={c.id}
              className="bg-white rounded-xl border border-ink/10 p-4 shadow-xs hover:border-pine/40 hover:shadow-md transition-all flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between gap-2 mb-2">
                  <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded bg-pine/10 text-pine">
                    {CONTACT_TYPE[c.contact_type]?.[locale] ?? c.contact_type}
                  </span>
                  <span
                    className="flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 shadow-2xs"
                    title="Индекс благонадежности ANYQ Trust Score"
                  >
                    🛡️ {c.trust_score}%
                  </span>
                </div>

                <h4 className="text-base font-bold text-ink">{c.name}</h4>
                {c.company_name && (
                  <p className="text-xs font-medium text-ink/70 mt-0.5">{c.company_name}</p>
                )}

                <div className="mt-3 space-y-1 text-xs text-ink/65">
                  <div className="flex items-center gap-1.5">
                    <span>📞</span>
                    <a href={`tel:${c.phone}`} className="text-pine underline">
                      {c.phone}
                    </a>
                  </div>
                  {c.bin_iin && (
                    <div className="flex items-center gap-1.5 font-mono text-[11px]">
                      <span>🆔</span> БИН/ИИН: {c.bin_iin}
                    </div>
                  )}
                  {c.email && (
                    <div className="flex items-center gap-1.5">
                      <span>✉️</span> {c.email}
                    </div>
                  )}
                  <div className="flex items-center gap-1.5">
                    <span>📍</span> {c.city}
                  </div>
                </div>

                {c.notes && (
                  <p className="mt-2.5 pt-2 border-t border-ink/5 text-xs text-ink/55 line-clamp-2">
                    {c.notes}
                  </p>
                )}
              </div>

              <div className="mt-4 pt-3 border-t border-ink/10 flex items-center justify-between text-[11px] bg-paper/40 -mx-4 -mb-4 p-3 rounded-b-xl">
                <div>
                  <span className="text-ink/45 block">Сделок:</span>
                  <span className="font-bold text-ink">{c.total_deals_count}</span>
                </div>
                <div className="text-right">
                  <span className="text-ink/45 block">Оборот:</span>
                  <span className="font-bold text-pine font-mono">
                    {c.total_turnover_kzt ? money(c.total_turnover_kzt, locale) : "0 ₸"}
                  </span>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
      <PageNav
        page={paged.page}
        pages={paged.pages}
        status={m.pageStatus.replace("{page}", String(paged.page + 1)).replace("{pages}", String(paged.pages))}
        prevLabel={m.pagePrev}
        nextLabel={m.pageNext}
        onPage={paged.setPage}
      />

      {/* New Contact Modal */}
      {isCreating && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 backdrop-blur-xs p-4 animate-fadeIn">
          <div className="w-full max-w-lg bg-white rounded-2xl p-6 shadow-2xl border border-ink/15">
            <h3 className="text-lg font-serif font-bold text-ink mb-1">Добавить контакт / компанию</h3>
            <p className="text-xs text-ink/60 mb-4">Внесите нового клиента, подрядчика или поставщика в базу.</p>

            <form onSubmit={handleCreateSubmit} className="space-y-3 text-xs">
              <div>
                <label className="block text-ink/60 font-medium mb-1">ФИО контактного лица:</label>
                <input
                  type="text"
                  placeholder="напр. Ерлан Смагулов"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-ink/60 font-medium mb-1">Компания / ТОО:</label>
                  <input
                    type="text"
                    placeholder="напр. ТОО 'СтройИнжиниринг'"
                    value={newCompany}
                    onChange={(e) => setNewCompany(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                  />
                </div>
                <div>
                  <label className="block text-ink/60 font-medium mb-1">БИН / ИИН:</label>
                  <input
                    type="text"
                    placeholder="12 цифр"
                    value={newBinIin}
                    onChange={(e) => setNewBinIin(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-ink/60 font-medium mb-1">Телефон:</label>
                  <input
                    type="tel"
                    placeholder="+7 (701) 000-00-00"
                    value={newPhone}
                    onChange={(e) => setNewPhone(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                    required
                  />
                </div>
                <div>
                  <label className="block text-ink/60 font-medium mb-1">Email:</label>
                  <input
                    type="email"
                    placeholder="name@mail.kz"
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-ink/60 font-medium mb-1">Роль контрагента:</label>
                  <select
                    value={newType}
                    onChange={(e) => setNewType(e.target.value as ContactType)}
                    className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                  >
                    <option value="client">Клиент / Заказчик</option>
                    <option value="contractor">Подрядчик / Проектировщик</option>
                    <option value="supplier">Поставщик материалов</option>
                    <option value="investor">Инвестор / Девелопер</option>
                  </select>
                </div>
                <div>
                  <label className="block text-ink/60 font-medium mb-1">Город / Регион:</label>
                  <input
                    type="text"
                    value={newCity}
                    onChange={(e) => setNewCity(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-ink/60 font-medium mb-1">Заметки / Особенности:</label>
                <textarea
                  rows={2}
                  placeholder="Дополнительные комментарии..."
                  value={newNotes}
                  onChange={(e) => setNewNotes(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-ink/15 rounded-lg bg-white"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-ink/10">
                <button
                  type="button"
                  onClick={() => setIsCreating(false)}
                  className="px-4 py-2 border border-ink/15 rounded-lg hover:bg-ink/5"
                >
                  Отмена
                </button>
                <button
                  type="submit"
                  disabled={createLock.pending}
                  className="min-h-11 rounded-lg bg-pine px-4 py-2 font-semibold text-white shadow-xs hover:bg-pine/90 disabled:opacity-50"
                >
                  Сохранить контакт
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
