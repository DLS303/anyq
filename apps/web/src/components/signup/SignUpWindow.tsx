"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { DemoBanner } from "@/components/signup/DemoBanner";
import { signupConfirm, signupStart } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { DEMO_MODE } from "@/lib/features";
import { SMS_LATER, demoContactError, detectContact } from "@/lib/signupContact";
import type { Locale } from "@/lib/types";

const ROLES = [
  { id: "supplier", label: "Поставщик" },
  { id: "contractor", label: "Исполнитель услуг" },
  { id: "customer", label: "Заказчик" },
] as const;

type RoleId = (typeof ROLES)[number]["id"];

export function SignUpWindow({ locale, demo = DEMO_MODE }: { locale: Locale; demo?: boolean }) {
  const router = useRouter();
  const { login } = useAuth();
  const [role, setRole] = useState<RoleId | "">("");
  const [contact, setContact] = useState("");
  const [name, setName] = useState("");
  const [consent, setConsent] = useState(false);
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<"role" | "contact" | "code" | "phone">("role");

  async function submitContact(event: React.FormEvent) {
    event.preventDefault();
    if (!role || busy) return;
    setError("");
    const parsed = detectContact(contact);
    if (parsed.channel === "invalid") {
      setError(parsed.error);
      return;
    }
    const blocked = demoContactError(parsed, demo);
    if (blocked) {
      setError(blocked);
      return;
    }
    if (!consent) {
      setError("Нужно согласие на обработку персональных данных");
      return;
    }
    setBusy(true);
    try {
      const data = await signupStart({
        role,
        contact: parsed.value,
        full_name: name.trim(),
        account_kind: "individual",
        consent_offer_pd: true,
      });
      if (data.channel === "phone") {
        setNotice(data.notice || SMS_LATER);
        setStep("phone");
        return;
      }
      setStep("code");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось создать аккаунт");
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setError("");
    setBusy(true);
    try {
      const parsed = detectContact(contact);
      if (parsed.channel !== "email") {
        setError(SMS_LATER);
        return;
      }
      const data = await signupConfirm(parsed.value, code.trim());
      login(data.user, data.token);
      router.push(`/${locale}/cabinet`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Неверный код");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-[390px] px-4 py-6">
      <div className="grid gap-4">
        <DemoBanner show={demo} />
        <h1 className="text-2xl font-bold text-slate-900">Регистрация</h1>
        {step === "role" ? (
          <div className="grid gap-3">
            {ROLES.map((item) => (
              <button
                key={item.id}
                type="button"
                className="btn-ice w-full font-semibold"
                onClick={() => {
                  setRole(item.id);
                  setError("");
                  setStep("contact");
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        ) : null}
        {step === "contact" ? (
          <form className="grid gap-3" onSubmit={submitContact}>
            <DemoBanner show={demo} />
            <label className="grid gap-1 text-sm text-slate-700">
              Телефон или почта
              <input
                className="rounded-xl border border-slate-300 px-3 py-3 text-base"
                value={contact}
                onChange={(event) => setContact(event.target.value)}
                autoComplete="username"
                inputMode="text"
                aria-label="Телефон или почта"
              />
            </label>
            <label className="grid gap-1 text-sm text-slate-700">
              Имя
              <input
                className="rounded-xl border border-slate-300 px-3 py-3 text-base"
                value={name}
                onChange={(event) => setName(event.target.value)}
                autoComplete="name"
                aria-label="Имя"
              />
            </label>
            <label className="flex items-start gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                className="mt-1"
                checked={consent}
                onChange={(event) => setConsent(event.target.checked)}
              />
              Согласие на обработку персональных данных
            </label>
            {error ? <p className="text-sm text-rose-700">{error}</p> : null}
            <button type="submit" className="btn-ice w-full font-semibold" disabled={busy}>
              Продолжить
            </button>
          </form>
        ) : null}
        {step === "code" ? (
          <form className="grid gap-3" onSubmit={submitCode}>
            <DemoBanner show={demo} />
            <label className="grid gap-1 text-sm text-slate-700">
              Код из письма
              <input
                className="rounded-xl border border-slate-300 px-3 py-3 text-base tracking-widest"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                aria-label="Код из письма"
              />
            </label>
            {error ? <p className="text-sm text-rose-700">{error}</p> : null}
            <button type="submit" className="btn-ice w-full font-semibold" disabled={busy}>
              Подтвердить
            </button>
          </form>
        ) : null}
        {step === "phone" ? (
          <div className="grid gap-3">
            <DemoBanner show={demo} />
            <p className="text-sm text-slate-800">{notice || SMS_LATER}</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
