import type { Locale, MaterialCat, Plot, Purpose, Relief, SpecCategory, Utility } from "./types";

export function money(n: number, locale: Locale) {
  const formatted = new Intl.NumberFormat(locale === "kk" ? "kk-KZ" : "ru-KZ").format(n);
  return `${formatted} ₸`;
}

export function ratingLabel(rating: number, count: number): string {
  if (!count) return "Новый";
  return Number(rating).toFixed(1);
}

export function reviewsLabel(count: number): string {
  const n = Math.abs(count) % 100;
  const n1 = n % 10;
  let word = "отзывов";
  if (n < 11 || n > 14) {
    if (n1 === 1) word = "отзыв";
    else if (n1 >= 2 && n1 <= 4) word = "отзыва";
  }
  return `${count} ${word}`;
}

export function titleOf(plot: Plot, locale: Locale) {
  return locale === "kk" ? plot.title_kk : plot.title_ru;
}

export function descOf(plot: Plot, locale: Locale) {
  return locale === "kk" ? plot.description_kk : plot.description_ru;
}

export function maskCadastral(no: string, verified: boolean) {
  if (verified) return no;
  if (no.length < 6) return "••-•••-•••-•••";
  return `${no.slice(0, 6)}-•••-•••`;
}

export const PURPOSE: Record<Purpose, { ru: string; kk: string }> = {
  izhs: { ru: "ИЖС", kk: "ЖЖҚ" },
  lph: { ru: "ЛПХ", kk: "ЖҚШ" },
  dacha: { ru: "Дача", kk: "Саяжай" },
  commercial: { ru: "Коммерция", kk: "Коммерция" },
  industrial: { ru: "Промзона", kk: "Өнеркәсіп" },
  recreation: { ru: "Рекреация", kk: "Рекреация" },
  investment: { ru: "Инвестмассив", kk: "Инвестмассив" },
};

export const UTILITY: Record<Utility, { ru: string; kk: string }> = {
  connected: { ru: "подключено", kk: "қосылған" },
  nearby: { ru: "точка рядом", kk: "жақын" },
  tu_received: { ru: "получены ТУ", kk: "ТУ алынған" },
  absent: { ru: "нет", kk: "жоқ" },
};

export const RELIEF: Record<Relief, { ru: string; kk: string }> = {
  flat: { ru: "ровный", kk: "тегіс" },
  slope: { ru: "уклон", kk: "еңіс" },
  steep: { ru: "крутой склон", kk: "тік беткей" },
};

export const MATERIAL_CAT: Record<MaterialCat, { ru: string; kk: string }> = {
  inert: { ru: "Инертные", kk: "Инертті" },
  concrete: { ru: "Бетон / ЖБИ", kk: "Бетон / ТББ" },
  brick: { ru: "Кирпич / блоки", kk: "Кірпіш / блоктар" },
  metal: { ru: "Металлопрокат", kk: "Металл" },
  lumber: { ru: "Пиломатериал", kk: "Ағаш" },
  roofing: { ru: "Кровля", kk: "Шатыр" },
  mix: { ru: "Сухие смеси", kk: "Құрғақ қоспа" },
};

export const MAT_ORDER: Record<string, { ru: string; kk: string }> = {
  requested: { ru: "заявка", kk: "өтінім" },
  confirmed: { ru: "подтверждён", kk: "расталды" },
  shipped: { ru: "в пути", kk: "жолда" },
  delivered: { ru: "доставлен", kk: "жеткізілді" },
  cancelled: { ru: "отмена", kk: "болдырылмады" },
};

export const CATEGORY: Record<SpecCategory, { ru: string; kk: string }> = {
  survey: { ru: "Изыскания", kk: "Іздестіру" },
  legal: { ru: "Юраудит", kk: "Заң аудит" },
  architecture: { ru: "Архитектура", kk: "Сәулет" },
  smr: { ru: "СМР", kk: "Құрылыс" },
  supervision: { ru: "Технадзор", kk: "Технадзор" },
  equipment: { ru: "Спецтехника", kk: "Техника" },
};

export const FUNNEL: Record<string, { ru: string; kk: string }> = {
  design: { ru: "Проектирование / ПСД", kk: "Жобалау" },
  construction: { ru: "Строительство / СМР", kk: "Құрылыс" },
  materials: { ru: "Поставка материалов", kk: "Материал жеткізу" },
  legal: { ru: "Юр. оформление / ГАСК", kk: "Заңдық рәсімдеу" },
};

export const PRODUCT_FUNNELS = ["construction", "design", "materials", "legal"] as const;

export const STAGE: Record<string, { ru: string; kk: string; color?: string }> = {
  lead: { ru: "Лид / Заявка", kk: "Лид / Өтінім", color: "border-blue-500 bg-blue-50/70 text-blue-900" },
  audit: { ru: "Аудит АИС ГЗК", kk: "АИС ГЗК аудиті", color: "border-cyan-500 bg-cyan-50/70 text-cyan-900" },
  viewing: { ru: "Осмотр / Выезд", kk: "Қарау / Шығу", color: "border-indigo-500 bg-indigo-50/70 text-indigo-900" },
  negotiation: { ru: "Переговоры", kk: "Келіссөз", color: "border-amber-500 bg-amber-50/70 text-amber-900" },
  deposit: { ru: "Задаток", kk: "Кепіл", color: "border-purple-500 bg-purple-50/70 text-purple-900" },
  won: { ru: "Успешная сделка", kk: "Сәтті мәміле", color: "border-emerald-500 bg-emerald-50/70 text-emerald-900" },
  lost: { ru: "Срыв / Отказ", kk: "Бас тарту", color: "border-rose-500 bg-rose-50/70 text-rose-900" },

  brief: { ru: "ТЗ и АПЗ", kk: "ТЖ мен СЖТ", color: "border-sky-500 bg-sky-50/70 text-sky-900" },
  sketch: { ru: "Эскизный проект", kk: "Эскиз жобасы", color: "border-teal-500 bg-teal-50/70 text-teal-900" },
  working: { ru: "Рабочий проект (РП)", kk: "Жұмыс жоба (ЖЖ)", color: "border-blue-500 bg-blue-50/70 text-blue-900" },
  expertise: { ru: "Экспертиза", kk: "Сараптама", color: "border-purple-500 bg-purple-50/70 text-purple-900" },
  handover: { ru: "Передача проекта", kk: "Жобаны тапсыру", color: "border-emerald-500 bg-emerald-50/70 text-emerald-900" },

  request: { ru: "Запрос сметы", kk: "Смета сұранысы", color: "border-sky-500 bg-sky-50/70 text-sky-900" },
  quote: { ru: "КП от подрядчика", kk: "Мердігердің КП", color: "border-teal-500 bg-teal-50/70 text-teal-900" },
  estimate: { ru: "Смета АВРС", kk: "АВРС сметасы", color: "border-indigo-500 bg-indigo-50/70 text-indigo-900" },
  contract: { ru: "Договор генподряда", kk: "Бас мердігер шарты", color: "border-amber-500 bg-amber-50/70 text-amber-900" },
  foundation: { ru: "Нулевой цикл", kk: "Нөлдік цикл", color: "border-orange-500 bg-orange-50/70 text-orange-900" },
  structure: { ru: "Каркас и кровля", kk: "Қаңқа мен шатыр", color: "border-violet-500 bg-violet-50/70 text-violet-900" },
  finishing: { ru: "Инженерия и отделка", kk: "Инженерия және әрлеу", color: "border-purple-500 bg-purple-50/70 text-purple-900" },
  works: { ru: "Строительные работы", kk: "Құрылыс жұмыстары", color: "border-blue-500 bg-blue-50/70 text-blue-900" },
  acceptance: { ru: "Акт ввода / Сдача", kk: "Пайдалануға беру актісі", color: "border-emerald-500 bg-emerald-50/70 text-emerald-900" },

  quote_req: { ru: "Запрос КП", kk: "КП сұранысы", color: "border-sky-500 bg-sky-50/70 text-sky-900" },
  invoice_sent: { ru: "Выставлен счет", kk: "Шот берілді", color: "border-amber-500 bg-amber-50/70 text-amber-900" },
  paid_reserved: { ru: "Оплачено / Резерв", kk: "Төленді / Резерв", color: "border-emerald-500 bg-emerald-50/70 text-emerald-900" },
  delivery: { ru: "Отгрузка и доставка", kk: "Жөнелту және жеткізу", color: "border-indigo-500 bg-indigo-50/70 text-indigo-900" },
  accepted: { ru: "Принято на объекте", kk: "Нысанда қабылданды", color: "border-teal-500 bg-teal-50/70 text-teal-900" },

  consult: { ru: "Консультация", kk: "Кеңес беру", color: "border-sky-500 bg-sky-50/70 text-sky-900" },
  docs_collection: { ru: "Сбор документов / ТУ", kk: "Құжаттар жинау", color: "border-teal-500 bg-teal-50/70 text-teal-900" },
  approval: { ru: "Согласование ГАСК", kk: "МСҚБ келісу", color: "border-amber-500 bg-amber-50/70 text-amber-900" },
  registered: { ru: "Зарегистрировано ЦОН", kk: "ХҚКО тіркелді", color: "border-emerald-500 bg-emerald-50/70 text-emerald-900" },
};

export const ACTIVITY_TYPE: Record<string, { ru: string; kk: string; icon: string }> = {
  call: { ru: "Звонок", kk: "Қоңырау", icon: "📞" },
  meeting: { ru: "Встреча", kk: "Кездесу", icon: "🤝" },
  site_visit: { ru: "Выезд на объект", kk: "Нысанға бару", icon: "📍" },
  task: { ru: "Задача", kk: "Тапсырма", icon: "📋" },
  invoice: { ru: "Счет / Оплата", kk: "Шот / Төлем", icon: "🧾" },
  note: { ru: "Заметка", kk: "Жазба", icon: "📝" },
};

export const LEAD_STATUS: Record<string, { ru: string; kk: string; color: string }> = {
  new: { ru: "Новый", kk: "Жаңа", color: "bg-blue-100 text-blue-800" },
  contacted: { ru: "В обработке", kk: "Өңделуде", color: "bg-amber-100 text-amber-800" },
  qualified: { ru: "Квалифицирован", kk: "Сараланған", color: "bg-purple-100 text-purple-800" },
  converted: { ru: "В сделке", kk: "Мәмілеге ауысқан", color: "bg-emerald-100 text-emerald-800" },
  junk: { ru: "Нецелевой", kk: "Мақсатты емес", color: "bg-gray-100 text-gray-800" },
};

export const CONTACT_TYPE: Record<string, { ru: string; kk: string }> = {
  client: { ru: "Заказчик", kk: "Тапсырыс беруші" },
  contractor: { ru: "Подрядчик / Проектировщик", kk: "Мердігер / Жобалаушы" },
  landowner: { ru: "Заказчик", kk: "Тапсырыс беруші" },
  supplier: { ru: "Поставщик материалов", kk: "Материал жеткізуші" },
  investor: { ru: "Инвестор / Девелопер", kk: "Инвестор / Девелопер" },
};

export const INVOICE_STATUS: Record<string, { ru: string; kk: string; color: string }> = {
  draft: { ru: "Черновик", kk: "Жоба", color: "bg-gray-100 text-gray-700" },
  sent: { ru: "Выставлен", kk: "Берілген", color: "bg-amber-100 text-amber-800" },
  paid: { ru: "Оплачен вручную", kk: "Қолмен төленген", color: "bg-emerald-100 text-emerald-800" },
  overdue: { ru: "Просрочен", kk: "Мерзімі өткен", color: "bg-rose-100 text-rose-800" },
  cancelled: { ru: "Отменён", kk: "Болдырылмады", color: "bg-gray-100 text-gray-500" },
};

export const ORDER_ST: Record<string, { ru: string; kk: string }> = {
  requested: { ru: "заявка", kk: "өтінім" },
  quoted: { ru: "КП", kk: "КП" },
  accepted: { ru: "принят", kk: "қабылданды" },
  in_progress: { ru: "в работе", kk: "жұмыста" },
  completed: { ru: "закрыт", kk: "жабылды" },
  cancelled: { ru: "отмена", kk: "болдырылмады" },
};

export const STATUS: Record<string, { ru: string; kk: string }> = {
  draft: { ru: "черновик", kk: "жоба" },
  pending: { ru: "на модерации", kk: "модерацияда" },
  needs_revision: { ru: "на доработке", kk: "толықтыру" },
  published: { ru: "опубликован", kk: "жарияланған" },
  rejected: { ru: "отклонён", kk: "қабылданбаған" },
  reserved: { ru: "бронь", kk: "бронь" },
  sold: { ru: "продан", kk: "сатылған" },
  archived: { ru: "архив", kk: "архив" },
};
