"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { fetchBootstrap, loginRequest, registerRequest } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { MATERIAL_CAT } from "@/lib/format";
import type { Locale, MaterialCat } from "@/lib/types";
import { t } from "@/i18n/messages";
import { PILOT_MODE } from "@/lib/pilot";
import { Building2, Lock, Mail, Truck } from "lucide-react";

type RegRole = "buyer" | "contractor" | "supplier";

const CATS: MaterialCat[] = ["concrete", "inert", "brick", "metal", "lumber", "roofing", "mix"];

export function LoginView({
  locale,
  initialMode = "register",
}: {
  locale: Locale;
  initialMode?: "login" | "register";
}) {
  const m = t(locale);
  const { login } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [company, setCompany] = useState("");
  const [companyBin, setCompanyBin] = useState("");
  const [city, setCity] = useState("");
  const [role, setRole] = useState<RegRole>("buyer");
  const [pilotOn, setPilotOn] = useState(false);
  const [skuTitle, setSkuTitle] = useState("");
  const [skuCategory, setSkuCategory] = useState<MaterialCat>("concrete");
  const [skuUnit, setSkuUnit] = useState("т");
  const [skuPrice, setSkuPrice] = useState("");
  const [skuStock, setSkuStock] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pdConsent, setPdConsent] = useState(false);
  const [aiConsent, setAiConsent] = useState(false);
  const [needsOwner, setNeedsOwner] = useState(false);
  const [registrationEnabled, setRegistrationEnabled] = useState(true);
  const [fieldError, setFieldError] = useState<Record<string, string>>({});
  const signUp = registrationEnabled;

  useEffect(() => {
    let stop = false;
    setPdConsent(false);
    setAiConsent(false);
    fetchBootstrap()
      .then((row) => {
        if (stop) return;
        const allow = row.registration_enabled !== false;
        setRegistrationEnabled(allow);
        setNeedsOwner(row.needs_owner);
        setMode(allow && (row.needs_owner || initialMode === "register") ? "register" : "login");
      })
      .catch(() => {
        if (!stop) setMode(PILOT_MODE ? "login" : initialMode);
      });
    return () => {
      stop = true;
    };
  }, [initialMode]);

  function toast(message: string) {
    if (typeof window === "undefined") return;
    window.dispatchEvent(new CustomEvent("anyq-toast", { detail: { message } }));
  }

  async function onLogin(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (!pdConsent) {
        setError(m.consentRequired);
        setBusy(false);
        return;
      }
      const res = await loginRequest(email, password, true, aiConsent);
      login(res.user, res.token);
      toast(`Добро пожаловать в ANYQ, ${res.user.full_name}`);
      router.push(`/${locale}/cabinet`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Неверный логин или пароль");
    } finally {
      setBusy(false);
    }
  }

  async function onRegister(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const bin = companyBin.replace(/\D/g, "");
    const price = Math.round(Number(skuPrice) || 0);
    const chosen = needsOwner ? "owner" : role;
    const next: Record<string, string> = {};
    if (company.trim().length < 2) next.company = "Укажите компанию";
    if (bin.length !== 12) next.bin = "БИН должен быть из 12 цифр";
    if (city.trim().length < 2) next.city = "Укажите город";
    if (fullName.trim().length < 2) next.name = "Укажите контактное лицо";
    if (phone.trim().length < 6) next.phone = "Укажите телефон";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) next.email = "Укажите почту";
    if (password.length < 6) next.password = "Пароль минимум 6 символов";
    if (!chosen) next.role = "Выберите роль";
    if (chosen === "supplier") {
      if (skuTitle.trim().length < 2) next.sku = "Укажите первую позицию для каталога";
      if (price <= 0) next.price = "Укажите цену позиции";
    }
    if (!pdConsent) next.consent = m.consentRequired;
    setFieldError(next);
    const order = ["company", "bin", "city", "phone", "name", "email", "password", "role", "sku", "price", "consent"];
    const firstInvalid = order.find((key) => next[key]);
    if (firstInvalid) {
      document.querySelector<HTMLElement>(`[data-field='${firstInvalid}']`)?.focus();
      return;
    }
    setBusy(true);
    try {
      const res = await registerRequest({
        email,
        password,
        full_name: fullName.trim(),
        phone: phone.trim(),
        company: company.trim(),
        company_bin: bin,
        city: city.trim() || "Алматы",
        role: chosen,
        pilot: needsOwner ? "" : pilotOn ? "engicon" : "",
        sku_title: chosen === "supplier" ? skuTitle.trim() : "",
        sku_category: skuCategory,
        sku_unit: skuUnit.trim() || "т",
        sku_price: chosen === "supplier" ? price : 0,
        sku_stock: chosen === "supplier" ? Number(skuStock) || 0 : 0,
        consent_offer_pd: true,
        consent_ai: aiConsent,
      });
      login(res.user, res.token);
      if (chosen === "supplier") {
        toast(pilotOn ? `«${skuTitle.trim()}» уже в каталоге. Пилот Engicon.` : `«${skuTitle.trim()}» уже в каталоге.`);
        router.push(`/${locale}/materials`);
      } else {
        toast(pilotOn ? `${company.trim()} в пилоте Engicon` : `${company.trim()} зарегистрирована`);
        router.push(`/${locale}/cabinet`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка регистрации");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto py-6 sm:py-10">
      <div className="grid md:grid-cols-[1.15fr_0.85fr] gap-8 items-start">
        <div className="glass-strong rounded-3xl p-6 sm:p-8 shadow-luxury border border-slate-200/90">
          {!signUp || needsOwner ? null : (
            <div className="flex items-center gap-2 mb-6 p-1 bg-slate-100 rounded-2xl w-fit border border-slate-200">
              <button
                type="button"
                className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                  mode === "register" ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-900"
                }`}
                onClick={() => {
                  setMode("register");
                  setPdConsent(false);
                }}
              >
                {m.register}
              </button>
              <button
                type="button"
                className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                  mode === "login" ? "bg-white text-slate-900 shadow-xs" : "text-slate-500 hover:text-slate-900"
                }`}
                onClick={() => {
                  setMode("login");
                  setPdConsent(false);
                }}
              >
                {m.navLogin}
              </button>
            </div>
          )}

          <h1 className="text-2xl font-bold text-slate-900 mb-1">
            {needsOwner && signUp ? m.ownerSetupTitle : !signUp || mode === "login" ? (PILOT_MODE ? m.pilotLoginTitle : m.loginTitle) : m.register}
          </h1>
          <p className="text-xs text-slate-500 mb-6">{needsOwner ? m.ownerSetupLead : PILOT_MODE ? m.pilotLoginLead : m.loginLead}</p>

          {!signUp || mode === "login" ? (
            <form onSubmit={onLogin} className="grid gap-3.5">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
                  Электронная почта
                </label>
                <div className="relative">
                  <Mail className="absolute left-3.5 top-3.5 h-4 w-4 text-slate-400" />
                  <input
                    className="w-full pl-10 pr-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900 focus:border-pine"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
                  {m.password}
                </label>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-3.5 h-4 w-4 text-slate-400" />
                  <input
                    className="w-full pl-10 pr-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900 focus:border-pine"
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </div>
              </div>

              <ConsentField locale={locale} checked={pdConsent} onChange={setPdConsent} />
              <AiConsentField locale={locale} checked={aiConsent} onChange={setAiConsent} />

              <button
                type="submit"
                disabled={busy || !pdConsent}
                className="btn-ice w-full font-bold text-sm shadow-navy justify-center mt-2 disabled:opacity-50"
              >
                {busy ? "Авторизация..." : m.navLogin}
              </button>
            </form>
          ) : (
            <form onSubmit={onRegister} noValidate className="grid gap-3" data-signup-form>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Компания</span>
                  <input
                    className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900"
                    required
                    autoComplete="organization"
                    data-field="company"
                    aria-invalid={fieldError.company ? true : undefined}
                    data-invalid={fieldError.company ? "true" : undefined}
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                  />
                  {fieldError.company ? <FieldNote>{fieldError.company}</FieldNote> : null}
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">БИН, 12 цифр</span>
                  <input
                    className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 font-mono text-sm text-slate-900"
                    required
                    inputMode="numeric"
                    autoComplete="off"
                    data-field="bin"
                    maxLength={12}
                    aria-invalid={fieldError.bin ? true : undefined}
                    data-invalid={fieldError.bin ? "true" : undefined}
                    value={companyBin}
                    onChange={(e) => setCompanyBin(e.target.value.replace(/\D/g, "").slice(0, 12))}
                  />
                  {fieldError.bin ? <FieldNote>{fieldError.bin}</FieldNote> : null}
                </label>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Город</span>
                  <input
                    className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900"
                    required
                    autoComplete="address-level2"
                    data-field="city"
                    aria-invalid={fieldError.city ? true : undefined}
                    data-invalid={fieldError.city ? "true" : undefined}
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                  />
                  {fieldError.city ? <FieldNote>{fieldError.city}</FieldNote> : null}
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">{m.phone}</span>
                  <input
                    className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900"
                    required
                    type="tel"
                    autoComplete="tel"
                    data-field="phone"
                    aria-invalid={fieldError.phone ? true : undefined}
                    data-invalid={fieldError.phone ? "true" : undefined}
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                  />
                  {fieldError.phone ? <FieldNote>{fieldError.phone}</FieldNote> : null}
                </label>
              </div>

              <label className="block">
                <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Контактное лицо</span>
                <input
                  className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900"
                  required
                  autoComplete="name"
                  data-field="name"
                  aria-invalid={fieldError.name ? true : undefined}
                  data-invalid={fieldError.name ? "true" : undefined}
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
                {fieldError.name ? <FieldNote>{fieldError.name}</FieldNote> : null}
              </label>

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Email</span>
                  <input
                    className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900"
                    type="email"
                    required
                    autoComplete="email"
                    data-field="email"
                    aria-invalid={fieldError.email ? true : undefined}
                    data-invalid={fieldError.email ? "true" : undefined}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                  {fieldError.email ? <FieldNote>{fieldError.email}</FieldNote> : null}
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Пароль, минимум 6 символов</span>
                  <input
                    className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900"
                    type="password"
                    required
                    minLength={6}
                    autoComplete="new-password"
                    data-field="password"
                    aria-invalid={fieldError.password ? true : undefined}
                    data-invalid={fieldError.password ? "true" : undefined}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  {fieldError.password ? <FieldNote>{fieldError.password}</FieldNote> : null}
                </label>
              </div>

              {needsOwner ? null : (
              <label className="block">
                <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Роль</span>
                <select
                  className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900"
                  required
                  value={role}
                  data-field="role"
                  aria-invalid={fieldError.role ? true : undefined}
                  data-invalid={fieldError.role ? "true" : undefined}
                  onChange={(e) => setRole(e.target.value as RegRole)}
                >
                  <option value="buyer">Заказчик</option>
                  <option value="contractor">Подрядчик</option>
                  <option value="supplier">Поставщик — позиция сразу в каталоге</option>
                </select>
                {fieldError.role ? <FieldNote>{fieldError.role}</FieldNote> : null}
              </label>
              )}

              {role === "supplier" && !needsOwner ? (
                <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white/70 p-3.5">
                  <p className="text-xs font-semibold text-slate-700">Первая позиция. Публикуется в каталог сразу, без модератора.</p>
                  <label className="block">
                    <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Категория</span>
                    <select
                      className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                      value={skuCategory}
                      onChange={(e) => setSkuCategory(e.target.value as MaterialCat)}
                    >
                      {CATS.map((cat) => (
                        <option key={cat} value={cat}>
                          {MATERIAL_CAT[cat].ru}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block">
                    <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Название позиции</span>
                    <input
                      className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900"
                      required
                      data-field="sku"
                      aria-invalid={fieldError.sku ? true : undefined}
                      data-invalid={fieldError.sku ? "true" : undefined}
                      value={skuTitle}
                      onChange={(e) => setSkuTitle(e.target.value)}
                    />
                    {fieldError.sku ? <FieldNote>{fieldError.sku}</FieldNote> : null}
                  </label>
                  <div className="grid grid-cols-3 gap-3">
                    <label className="block">
                      <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Ед.</span>
                      <input
                        className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                        value={skuUnit}
                        onChange={(e) => setSkuUnit(e.target.value)}
                      />
                    </label>
                    <label className="block">
                      <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Цена, ₸</span>
                      <input
                        className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900"
                        inputMode="numeric"
                        required
                        data-field="price"
                        aria-invalid={fieldError.price ? true : undefined}
                        data-invalid={fieldError.price ? "true" : undefined}
                        value={skuPrice}
                        onChange={(e) => setSkuPrice(e.target.value.replace(/[^\d]/g, ""))}
                      />
                      {fieldError.price ? <FieldNote>{fieldError.price}</FieldNote> : null}
                    </label>
                    <label className="block">
                      <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Остаток</span>
                      <input
                        className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                        inputMode="decimal"
                        value={skuStock}
                        onChange={(e) => setSkuStock(e.target.value.replace(/[^\d.]/g, ""))}
                      />
                    </label>
                  </div>
                </div>
              ) : null}

              {needsOwner ? null : (
              <label className="flex items-start gap-2.5 text-sm text-slate-700">
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 accent-[#2F5B8A]"
                  checked={pilotOn}
                  onChange={(e) => setPilotOn(e.target.checked)}
                />
                <span>Пилот Engicon. Компания участвует в пилотном проекте.</span>
              </label>
              )}

              <ConsentField locale={locale} checked={pdConsent} onChange={setPdConsent} invalid={Boolean(fieldError.consent)} />
              {fieldError.consent ? <FieldNote>{fieldError.consent}</FieldNote> : null}
              <AiConsentField locale={locale} checked={aiConsent} onChange={setAiConsent} />

              <button type="submit" disabled={busy} className="btn-ice mt-1 w-full justify-center text-sm font-bold shadow-navy disabled:opacity-50">
                {busy ? "Регистрация..." : role === "supplier" ? "Зарегистрировать и открыть каталог" : m.register}
              </button>
            </form>
          )}

          {error ? (
            <p role="alert" className="text-xs font-semibold text-red-600 bg-red-50 p-3 rounded-xl border border-red-200 mt-4">
              {error}
            </p>
          ) : null}
        </div>

        <aside className="glass-strong rounded-3xl p-6 sm:p-8 shadow-luxury border border-slate-200/90">
          <div className="flex items-center gap-2 mb-3">
            <Building2 className="h-5 w-5 text-pine" />
            <h2 className="text-lg font-bold text-slate-900">{needsOwner ? m.ownerSetupTitle : PILOT_MODE ? m.pilotLoginTitle : m.demoHint}</h2>
          </div>
          <p className="text-sm text-slate-600 leading-relaxed">
            {needsOwner
              ? m.ownerSetupLead
              : PILOT_MODE
              ? m.pilotLoginAside
              : "Компания входит по своим реквизитам. Поставщик указывает первую позицию, и она сразу появляется в каталоге материалов."}
          </p>
          {!signUp || needsOwner ? null : (
            <>
              <ul className="mt-5 grid gap-3 text-sm text-slate-700">
                <li className="flex gap-2">
                  <Truck className="h-4 w-4 mt-0.5 text-pine shrink-0" />
                  <span>Поставщик: БИН, город, цена и остаток. Модератор не нужен.</span>
                </li>
                <li className="flex gap-2">
                  <Building2 className="h-4 w-4 mt-0.5 text-pine shrink-0" />
                  <span>Заказчик Engicon и подрядчик попадают в кабинет и видят каталог.</span>
                </li>
              </ul>
              <p className="mt-5 text-xs text-slate-500 leading-relaxed">
                Оплата в этом пилоте не подключена. Заказ поставки фиксируется как заявка.
              </p>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}

function AiConsentField({
  locale,
  checked,
  onChange,
}: {
  locale: Locale;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  const m = t(locale);
  return (
    <label className="flex items-start gap-2.5 text-sm text-slate-700">
      <input
        type="checkbox"
        className="mt-1 h-4 w-4 accent-[#2F5B8A]"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        {m.consentAiAllow}{" "}
        <Link href={`/${locale}/legal/ai-consent`} className="underline text-pine" target="_blank" rel="noopener noreferrer">
          {m.consentAiDoc}
        </Link>
        . {m.consentAiHint}
      </span>
    </label>
  );
}

function FieldNote({ children }: { children: string }) {
  return (
    <p role="alert" className="mt-1 text-xs font-semibold text-red-700">
      {children}
    </p>
  );
}

function ConsentField({
  locale,
  checked,
  onChange,
  invalid = false,
}: {
  locale: Locale;
  checked: boolean;
  onChange: (value: boolean) => void;
  invalid?: boolean;
}) {
  return (
    <label className="flex items-start gap-2.5 text-sm text-slate-700">
      <input
        type="checkbox"
        className="mt-1 h-4 w-4 accent-[#2F5B8A]"
        data-field="consent"
        aria-invalid={invalid || undefined}
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        {locale === "kk" ? (
          <>
            Мен{" "}
            <Link href={`/${locale}/legal/privacy`} className="underline text-pine" target="_blank" rel="noopener noreferrer">
              Құпиялылық саясатын
            </Link>{" "}
            қабылдаймын және{" "}
            <Link href={`/${locale}/legal/pd-consent`} className="underline text-pine" target="_blank" rel="noopener noreferrer">
              дербес деректерді өңдеуге келісім
            </Link>{" "}
            беремін.
          </>
        ) : (
          <>
            Я принимаю{" "}
            <Link href={`/${locale}/legal/privacy`} className="underline text-pine" target="_blank" rel="noopener noreferrer">
              Политику конфиденциальности
            </Link>{" "}
            и даю{" "}
            <Link href={`/${locale}/legal/pd-consent`} className="underline text-pine" target="_blank" rel="noopener noreferrer">
              согласие на обработку персональных данных
            </Link>
            .
          </>
        )}
      </span>
    </label>
  );
}
