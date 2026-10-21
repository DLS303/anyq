"use client";

import { useEffect, useState } from "react";
import { fetchProfile, patchProfile, type SupplierProfileData } from "@/lib/api";

const EMPTY: SupplierProfileData = {
  full_name: "",
  city: "",
  categories: "",
  e_invoice: "",
  bin: "",
  vat_included: null,
  vat_label: "НДС не указан",
};

export function SupplierProfile() {
  const [profile, setProfile] = useState<SupplierProfileData>(EMPTY);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let stop = false;
    fetchProfile()
      .then((data) => {
        if (!stop) setProfile(data);
      })
      .catch((cause: unknown) => {
        if (!stop) setError(cause instanceof Error ? cause.message : "Не удалось открыть профиль");
      });
    return () => {
      stop = true;
    };
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const vat = profile.vat_included === true ? "yes" : profile.vat_included === false ? "no" : "unset";
      const next = await patchProfile({
        full_name: profile.full_name,
        city: profile.city,
        categories: profile.categories,
        e_invoice: profile.e_invoice,
        company_bin: profile.bin,
        vat,
      });
      setProfile(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось сохранить");
    } finally {
      setBusy(false);
    }
  }

  function field(label: string, key: "full_name" | "city" | "categories" | "e_invoice" | "bin") {
    return (
      <label className="grid gap-1 text-sm text-slate-700">
        {label}
        <input
          className="rounded-xl border border-slate-300 px-3 py-3"
          aria-label={label}
          value={profile[key]}
          onChange={(event) => setProfile({ ...profile, [key]: event.target.value })}
        />
      </label>
    );
  }

  return (
    <form className="glass-strong grid gap-3 rounded-3xl border border-slate-200 p-6 shadow-luxury" onSubmit={save}>
      <h2 className="text-lg font-bold text-slate-900">Профиль поставщика</h2>
      <p className="text-sm text-slate-600">{profile.vat_label || "НДС не указан"}</p>
      {field("Имя", "full_name")}
      {field("Город", "city")}
      {field("Категории", "categories")}
      {field("Электронная счёт-фактура", "e_invoice")}
      {field("БИН", "bin")}
      <label className="grid gap-1 text-sm text-slate-700">
        НДС
        <select
          className="rounded-xl border border-slate-300 px-3 py-3"
          aria-label="НДС"
          value={profile.vat_included === true ? "yes" : profile.vat_included === false ? "no" : "unset"}
          onChange={(event) => {
            const value = event.target.value;
            setProfile({
              ...profile,
              vat_included: value === "yes" ? true : value === "no" ? false : null,
              vat_label: value === "yes" ? "с НДС" : value === "no" ? "без НДС" : "НДС не указан",
            });
          }}
        >
          <option value="unset">НДС не указан</option>
          <option value="yes">с НДС</option>
          <option value="no">без НДС</option>
        </select>
      </label>
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      <button type="submit" className="btn-ice font-semibold" disabled={busy}>
        Сохранить
      </button>
    </form>
  );
}
