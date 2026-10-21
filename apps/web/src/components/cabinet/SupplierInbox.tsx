"use client";

export type InboxRequest = {
  id: string;
  title: string;
  project_title?: string;
  number?: number;
};

export function SupplierInbox({ items, error }: { items: InboxRequest[]; error?: string }) {
  return (
    <section className="glass-strong rounded-3xl border border-slate-200 p-6 shadow-luxury">
      <h2 className="text-lg font-bold text-slate-900">Входящие заявки</h2>
      {error ? <p className="mt-3 text-sm text-rose-700">{error}</p> : null}
      {items.length === 0 ? <p className="mt-3 text-sm text-slate-500">Пока нет заявок</p> : null}
      <ul className="mt-3 grid gap-2">
        {items.map((item) => (
          <li key={item.id} className="rounded-2xl border border-slate-200 px-3 py-3 text-sm">
            <div className="font-semibold text-slate-900">{item.title}</div>
            {item.project_title ? <div className="text-slate-500">{item.project_title}</div> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
