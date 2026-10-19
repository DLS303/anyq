"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { initNativeShell, isNativeApp, registerWebServiceWorker, watchNativeNetwork } from "@/lib/native";

export function NativeShell() {
  const pathname = usePathname() || "/ru";
  const [native, setNative] = useState(false);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    const inside = isNativeApp();
    setNative(inside);
    if (inside) {
      initNativeShell();
      void watchNativeNetwork(setOffline);
      return;
    }
    registerWebServiceWorker();
  }, []);

  if (!native || !offline) return null;
  const kk = pathname.startsWith("/kk");
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-[#EFE8DE] px-6 text-[#1C1915]">
      <div className="w-full max-w-[360px] text-center">
        <div className="mx-auto grid h-[72px] w-[72px] place-items-center rounded-[18px] bg-[#2F5B8A] text-[28px] font-semibold text-[#F4F7FA]">
          Ан
        </div>
        <h1 className="mt-5 text-[28px] font-semibold tracking-tight">{kk ? "Интернет жоқ" : "Нет интернета"}</h1>
        <p className="mt-3 text-base leading-6 text-[#1C1915]/70">
          {kk ? "Байланысты тексеріп, қайта көріңіз." : "Проверьте соединение и попробуйте снова."}
        </p>
        <button
          type="button"
          className="mt-7 inline-flex min-h-12 w-full items-center justify-center rounded-full bg-[#2F5B8A] px-6 text-base font-semibold text-[#F4F7FA]"
          onClick={() => window.location.reload()}
        >
          {kk ? "Қайталау" : "Повторить"}
        </button>
      </div>
    </div>
  );
}
