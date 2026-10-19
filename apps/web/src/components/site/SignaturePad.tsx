"use client";

import { useEffect, useRef, useState } from "react";

interface Props {
  contractorName: string;
  customerName: string;
  onSave: (contractor: string, customer: string) => void;
  onClose: () => void;
  initialContractor?: string;
  initialCustomer?: string;
}

type Role = "contractor" | "customer";

export function SignaturePad({
  contractorName,
  customerName,
  onSave,
  onClose,
  initialContractor = "",
  initialCustomer = "",
}: Props) {
  const [SigCanvas, setSigCanvas] = useState<any>(null);
  const [activeRole, setActiveRole] = useState<Role>("contractor");
  const contractorRef = useRef<any>(null);
  const customerRef = useRef<any>(null);
  const [contractorDone, setContractorDone] = useState(!!initialContractor);
  const [customerDone, setCustomerDone] = useState(!!initialCustomer);
  const [contractorDataUrl, setContractorDataUrl] = useState(initialContractor);
  const [customerDataUrl, setCustomerDataUrl] = useState(initialCustomer);

  useEffect(() => {
    import("react-signature-canvas").then((m) => setSigCanvas(() => m.default));
  }, []);

  const activeRef = activeRole === "contractor" ? contractorRef : customerRef;

  function clearActive() {
    activeRef.current?.clear();
    if (activeRole === "contractor") { setContractorDone(false); setContractorDataUrl(""); }
    else { setCustomerDone(false); setCustomerDataUrl(""); }
  }

  function saveActive() {
    if (!activeRef.current || activeRef.current.isEmpty()) return;
    const url = activeRef.current.getTrimmedCanvas().toDataURL("image/png");
    if (activeRole === "contractor") { setContractorDataUrl(url); setContractorDone(true); }
    else { setCustomerDataUrl(url); setCustomerDone(true); }
  }

  function handleDone() {
    // auto-save current pad if not empty
    if (activeRef.current && !activeRef.current.isEmpty()) {
      const url = activeRef.current.getTrimmedCanvas().toDataURL("image/png");
      const c = activeRole === "contractor" ? url : contractorDataUrl;
      const k = activeRole === "customer" ? url : customerDataUrl;
      onSave(c, k);
    } else {
      onSave(contractorDataUrl, customerDataUrl);
    }
    onClose();
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-ink/50 backdrop-blur-xs p-4">
      <div className="w-full max-w-lg bg-white rounded-2xl shadow-2xl border border-ink/15 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-ink/10 bg-paper/60">
          <div>
            <h3 className="font-serif font-bold text-ink">✍️ Подпись</h3>
            <p className="text-xs text-ink/50 mt-0.5">Подпишите акт пальцем или мышью</p>
          </div>
          <button type="button" onClick={onClose} className="text-ink/40 hover:text-ink text-xl">✕</button>
        </div>

        {/* Role tabs */}
        <div className="flex border-b border-ink/10">
          {(["contractor", "customer"] as Role[]).map((role) => {
            const name = role === "contractor" ? contractorName : customerName;
            const done = role === "contractor" ? contractorDone : customerDone;
            return (
              <button
                key={role}
                type="button"
                onClick={() => setActiveRole(role)}
                className={`flex-1 py-2.5 text-xs font-semibold border-b-2 transition-colors flex items-center justify-center gap-1.5 ${
                  activeRole === role
                    ? "border-pine text-pine"
                    : "border-transparent text-ink/50 hover:text-ink"
                }`}
              >
                {done ? <span className="text-emerald-500">✓</span> : null}
                {role === "contractor" ? "Подрядчик" : "Заказчик"}: {name}
              </button>
            );
          })}
        </div>

        {/* Signature Canvas */}
        <div className="px-5 py-4">
          <div className="border-2 border-dashed border-ink/20 rounded-xl overflow-hidden bg-gray-50 relative" style={{ height: 180 }}>
            {SigCanvas ? (
              <>
                {activeRole === "contractor" && !contractorDone && (
                  <SigCanvas
                    ref={contractorRef}
                    canvasProps={{ width: 460, height: 176, className: "w-full h-full" }}
                    backgroundColor="rgb(249,250,251)"
                    penColor="#1a1a2e"
                  />
                )}
                {activeRole === "customer" && !customerDone && (
                  <SigCanvas
                    ref={customerRef}
                    canvasProps={{ width: 460, height: 176, className: "w-full h-full" }}
                    backgroundColor="rgb(249,250,251)"
                    penColor="#1a1a2e"
                  />
                )}
                {/* Show saved signature */}
                {activeRole === "contractor" && contractorDone && contractorDataUrl && (
                  <div className="absolute inset-0 flex flex-col items-center justify-center bg-emerald-50">
                    <img src={contractorDataUrl} alt="Подпись подрядчика" className="max-h-36 object-contain" />
                    <p className="text-xs text-emerald-600 mt-1 font-semibold">✓ Подпись сохранена</p>
                  </div>
                )}
                {activeRole === "customer" && customerDone && customerDataUrl && (
                  <div className="absolute inset-0 flex flex-col items-center justify-center bg-emerald-50">
                    <img src={customerDataUrl} alt="Подпись заказчика" className="max-h-36 object-contain" />
                    <p className="text-xs text-emerald-600 mt-1 font-semibold">✓ Подпись сохранена</p>
                  </div>
                )}
              </>
            ) : (
              <div className="absolute inset-0 flex items-center justify-center text-ink/30 text-sm">Загрузка...</div>
            )}
            {/* Guide line */}
            {!( (activeRole === "contractor" && contractorDone) || (activeRole === "customer" && customerDone) ) && (
              <div className="absolute bottom-8 left-8 right-8 border-b border-ink/20 pointer-events-none" />
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 mt-3">
            <button type="button" onClick={clearActive}
              className="px-3 py-1.5 border border-ink/15 text-xs rounded-lg hover:bg-ink/5">
              🗑 Очистить
            </button>
            <button type="button" onClick={saveActive}
              className="px-3 py-1.5 bg-sky-600 text-white text-xs font-semibold rounded-lg hover:bg-sky-700 shadow-xs">
              💾 Сохранить подпись
            </button>
            <div className="ml-auto flex gap-2">
              <button type="button" onClick={onClose}
                className="px-4 py-1.5 border border-ink/15 text-xs rounded-lg hover:bg-ink/5">
                Отмена
              </button>
              <button type="button" onClick={handleDone}
                className={`px-4 py-1.5 text-white text-xs font-bold rounded-lg shadow-xs ${
                  contractorDone || customerDone ? "bg-pine hover:bg-pine/90" : "bg-ink/30 cursor-not-allowed"
                }`}
                disabled={!contractorDone && !customerDone}
              >
                ✅ Готово
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
