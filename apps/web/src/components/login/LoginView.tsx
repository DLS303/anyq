"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { loginRequest, registerRequest } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { MATERIAL_CAT } from "@/lib/format";
import type { Locale, MaterialCat } from "@/lib/types";
import { t } from "@/i18n/messages";
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
  const [city, setCity] = useState("Алматы");
  const [role, setRole] = useState<RegRole>("supplier");
  const [pilotOn, setPilotOn] = useState(true);
  const [skuTitle, setSkuTitle] = useState("");
  const [skuCategory, setSkuCategory] = useState<MaterialCat>("concrete");
  const [skuUnit, setSkuUnit] = useState("т");
  const [skuPrice, setSkuPrice] = useState("");
  const [skuStock, setSkuStock] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pdConsent, setPdConsent] = useState(false);

  useEffect(() => {
    setMode(initialMode);
    setPdConsent(false);
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
        setError(locale === "kk" ? "Дербес деректерді өңдеуге келісім керек" : "Нужно согласие на обработку персональных данных");
        setBusy(false);
        return;
      }
      const res = await loginRequest(email, password, true);
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
    if (company.trim().length < 2) {
      setError("Укажите компанию");
      return;
    }
    if (bin.length !== 12) {
      setError("БИН должен быть из 12 цифр");
      return;
    }
    if (fullName.trim().length < 2) {
      setError("Укажите контактное лицо");
      return;
    }
    if (phone.trim().length < 6) {
      setError("Укажите телефон");
      return;
    }
    if (role === "supplier") {
      if (skuTitle.trim().length < 2) {
        setError("Укажите первую позицию для каталога");
        return;
      }
      if (price <= 0) {
        setError("Укажите цену позиции");
        return;
      }
    }
    if (!pdConsent) {
      setError(locale === "kk" ? "Дербес деректерді өңдеуге келісім керек" : "Нужно согласие на обработку персональных данных");
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
        role,
        pilot: pilotOn ? "engicon" : "",
        sku_title: role === "supplier" ? skuTitle.trim() : "",
        sku_category: skuCategory,
        sku_unit: skuUnit.trim() || "т",
        sku_price: role === "supplier" ? price : 0,
        sku_stock: role === "supplier" ? Number(skuStock) || 0 : 0,
        consent_offer_pd: true,
      });
      login(res.user, res.token);
      if (role === "supplier") {
        toast(`«${skuTitle.trim()}» уже в каталоге. Пилот Engicon.`);
        router.push(`/${locale}/materials`);
      } else {
        toast(`${company.trim()} в пилоте Engicon`);
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

          <h1 className="text-2xl font-bold text-slate-900 mb-1">
            {mode === "login" ? "Вход в ANYQ" : "Регистрация компании"}
          </h1>
          <p className="text-xs text-slate-500 mb-6">{m.loginLead}</p>

          {mode === "login" ? (
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
                    placeholder="name@company.kz"
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
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </div>
              </div>

              <ConsentField locale={locale} checked={pdConsent} onChange={setPdConsent} />

              <button
                type="submit"
                disabled={busy || !pdConsent}
                className="btn-ice w-full font-bold text-sm shadow-navy justify-center mt-2 disabled:opacity-50"
              >
                {busy ? "Авторизация..." : m.navLogin}
              </button>
            </form>
          ) : (
            <form onSubmit={onRegister} className="grid gap-3">
              <div className="grid sm:grid-cols-2 gap-3">
                <label className="block">
                  <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Компания</span>
                  <input
                    className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                    required
                    autoComplete="organization"
                    placeholder="ТОО «Название»"
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                  />
                </label>
                <label className="block">
                  <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">БИН</span>
                  <input
                    className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900 font-mono"
                    required
                    inputMode="numeric"
                    autoComplete="off"
                    maxLength={12}
                    placeholder="12 цифр"
                    value={companyBin}
                    onChange={(e) => setCompanyBin(e.target.value.replace(/\D/g, "").slice(0, 12))}
                  />
                </label>
              </div>

              <div className="grid sm:grid-cols-2 gap-3">
                <label className="block">
                  <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Город</span>
                  <input
                    className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                    required
                    autoComplete="address-level2"
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                  />
                </label>
                <label className="block">
                  <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">{m.phone}</span>
                  <input
                    className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                    required
                    type="tel"
                    autoComplete="tel"
                    placeholder="+7 707 000 00 00"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                  />
                </label>
              </div>

              <label className="block">
                <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Контактное лицо</span>
                <input
                  className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                  required
                  autoComplete="name"
                  placeholder="Имя и фамилия"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </label>

              <div className="grid sm:grid-cols-2 gap-3">
                <label className="block">
                  <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Email</span>
                  <input
                    className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                    type="email"
                    required
                    autoComplete="email"
                    placeholder="email@company.kz"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </label>
                <label className="block">
                  <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">{m.password}</span>
                  <input
                    className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                    type="password"
                    required
                    minLength={6}
                    autoComplete="new-password"
                    placeholder="Минимум 6 символов"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </label>
              </div>

              <label className="block">
                <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Роль в пилоте</span>
                <select
                  className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                  value={role}
                  onChange={(e) => setRole(e.target.value as RegRole)}
                >
                  <option value="supplier">Поставщик — позиция сразу в каталоге</option>
                  <option value="buyer">Заказчик Engicon</option>
                  <option value="contractor">Подрядчик</option>
                </select>
              </label>

              {role === "supplier" ? (
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
                      className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                      required
                      placeholder="Цемент М500"
                      value={skuTitle}
                      onChange={(e) => setSkuTitle(e.target.value)}
                    />
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
                        className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                        inputMode="numeric"
                        required
                        placeholder="28500"
                        value={skuPrice}
                        onChange={(e) => setSkuPrice(e.target.value.replace(/[^\d]/g, ""))}
                      />
                    </label>
                    <label className="block">
                      <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Остаток</span>
                      <input
                        className="w-full px-3.5 py-2.5 text-sm border border-slate-200 rounded-xl bg-white text-slate-900"
                        inputMode="decimal"
                        placeholder="0"
                        value={skuStock}
                        onChange={(e) => setSkuStock(e.target.value.replace(/[^\d.]/g, ""))}
                      />
                    </label>
                  </div>
                </div>
              ) : null}

              <label className="flex items-start gap-2.5 text-sm text-slate-700">
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 accent-[#2F5B8A]"
                  checked={pilotOn}
                  onChange={(e) => setPilotOn(e.target.checked)}
                />
                <span>Пилот Engicon. Компания участвует в пилотном проекте.</span>
              </label>

              <ConsentField locale={locale} checked={pdConsent} onChange={setPdConsent} />

              <button type="submit" disabled={busy || !pdConsent} className="btn-ice w-full font-bold text-sm shadow-navy justify-center mt-1 disabled:opacity-50">
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
            <h2 className="text-lg font-bold text-slate-900">Пилот с Engicon</h2>
          </div>
          <p className="text-sm text-slate-600 leading-relaxed">
            Компания входит по своим реквизитам. Поставщик указывает первую позицию, и она сразу появляется в каталоге материалов.
          </p>
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
            Оплата и эскроу в этом пилоте не подключены. Заказ поставки фиксируется как заявка.
          </p>
        </aside>
      </div>
    </div>
  );
}

function ConsentField({
  locale,
  checked,
  onChange,
}: {
  locale: Locale;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-2.5 text-sm text-slate-700">
      <input
        type="checkbox"
        className="mt-1 h-4 w-4 accent-[#2F5B8A]"
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
