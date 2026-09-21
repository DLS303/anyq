"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchDemoUsers, loginRequest, registerRequest } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Locale } from "@/lib/types";
import { t } from "@/i18n/messages";

type Demo = { email: string; full_name: string; role: string };

function roleName(role: string, locale: Locale) {
  const m = t(locale);
  if (role === "owner") return m.owner;
  if (role === "moderator") return m.moderator;
  if (role === "admin") return m.admin;
  if (role === "specialist") return m.specialist;
  if (role === "contractor") return m.contractor;
  if (role === "supervisor") return m.supervisor;
  if (role === "supplier") return m.supplier;
  return m.buyer;
}

export function LoginView({ locale }: { locale: Locale }) {
  const m = t(locale);
  const { login } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [role, setRole] = useState<"buyer" | "owner" | "supplier">("buyer");
  const [error, setError] = useState("");
  const [demos, setDemos] = useState<Demo[]>([]);

  useEffect(() => {
    fetchDemoUsers()
      .then((data) => setDemos(data as unknown as Demo[]))
      .catch(() => setDemos([]));
  }, []);

  async function onLogin(e?: React.FormEvent, preset?: string) {
    e?.preventDefault();
    setError("");
    try {
      const res = await loginRequest(preset || email, preset ? "demo123" : password);
      login(res.user, res.token);
      router.push(`/${locale}/cabinet`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    }
  }

  async function onRegister(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const res = await registerRequest({
        email,
        password,
        full_name: fullName,
        phone,
        role,
      });
      login(res.user, res.token);
      router.push(`/${locale}/cabinet`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
    }
  }

  return (
    <div className="grid md:grid-cols-[1fr_1fr] gap-10 max-w-4xl">
      <div>
        <div className="flex gap-3 mb-4 text-sm">
          <button type="button" className={mode === "login" ? "underline" : "text-ink/50"} onClick={() => setMode("login")}>
            {m.navLogin}
          </button>
          <button type="button" className={mode === "register" ? "underline" : "text-ink/50"} onClick={() => setMode("register")}>
            {m.register}
          </button>
        </div>
        <p className="text-ink/60 mb-4">{m.loginLead}</p>
        {mode === "login" ? (
          <form onSubmit={onLogin} className="grid gap-3">
            <input className="border border-ink/15 px-3 py-2" type="email" required placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            <input className="border border-ink/15 px-3 py-2" type="password" required placeholder={m.password} value={password} onChange={(e) => setPassword(e.target.value)} />
            <button className="btn-ice">{m.navLogin}</button>
          </form>
        ) : (
          <form onSubmit={onRegister} className="grid gap-3">
            <input className="border border-ink/15 px-3 py-2" required placeholder={m.fullName} value={fullName} onChange={(e) => setFullName(e.target.value)} />
            <input className="border border-ink/15 px-3 py-2" type="email" required placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            <input className="border border-ink/15 px-3 py-2" placeholder={m.phone} value={phone} onChange={(e) => setPhone(e.target.value)} />
            <input className="border border-ink/15 px-3 py-2" type="password" required minLength={6} placeholder={m.password} value={password} onChange={(e) => setPassword(e.target.value)} />
            <select className="border border-ink/15 px-3 py-2" value={role} onChange={(e) => setRole(e.target.value as "buyer" | "owner" | "supplier")}>
              <option value="buyer">{m.buyer}</option>
              <option value="owner">{m.owner}</option>
              <option value="supplier">{m.supplier}</option>
            </select>
            <button className="btn-ice">{m.register}</button>
          </form>
        )}
        {error ? <p className="text-clay text-sm mt-3">{error}</p> : null}
      </div>
      <div>
        <p className="text-xs uppercase tracking-wider text-ink/45 mb-3">{m.demoHint}</p>
        <div className="grid gap-2">
          {demos.map((u) => (
            <button
              key={u.email}
              type="button"
              onClick={() => onLogin(undefined, u.email)}
              className="glass rounded-frost px-4 py-3 text-left hover:border-ice/40"
            >
              <span className="block font-medium">{u.full_name}</span>
              <span className="text-sm text-ink/50">
                {roleName(u.role, locale)} · {u.email}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
