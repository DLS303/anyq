import Link from "next/link";

export default function LocaleNotFound() {
  return (
    <div className="min-h-[60vh] grid place-items-center p-6">
      <div className="max-w-md w-full text-center space-y-4">
        <div className="inline-grid h-16 w-16 place-items-center rounded-2xl bg-amber-50 text-amber-700 font-bold text-2xl border border-amber-200">
          404
        </div>
        <h1 className="text-2xl font-bold text-slate-900">Бет табылмады / Страница не найдена</h1>
        <p className="text-sm text-slate-500">Бұл бөлім жоқ немесе жаңартылуда / Раздел не существует или находится в разработке.</p>
        <div className="pt-2">
          <Link
            href="/ru"
            className="inline-flex items-center justify-center px-5 py-2.5 rounded-full bg-[#2F5B8A] text-white text-sm font-semibold hover:bg-[#24476c] transition-colors shadow-sm"
          >
            Басты бетке оралу / На главную
          </Link>
        </div>
      </div>
    </div>
  );
}
