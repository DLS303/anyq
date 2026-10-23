export const DEMO_BANNER_TEXT =
  "Демо-версия: данные могут быть сброшены, не вводите настоящие персональные данные";
export const SMS_LATER = "Подтверждение по SMS появится позже";
export const DEMO_EMAIL_ERROR = "В демо-версии регистрация только для адресов @demo.superapp";
export const DEMO_PHONE_STUB_CODE = "000000";
export const DEMO_PHONE_STUB_TEXT = `Демо: SMS не отправляется. Код подтверждения ${DEMO_PHONE_STUB_CODE}`;

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export type Contact =
  | { channel: "email"; value: string }
  | { channel: "phone"; value: string }
  | { channel: "invalid"; error: string };

export function normalizePhone(raw: string): string | null {
  let digits = (raw || "").replace(/\D/g, "");
  if (digits.length === 11 && digits.startsWith("8")) digits = `7${digits.slice(1)}`;
  else if (digits.length === 10) digits = `7${digits}`;
  if (digits.length !== 11 || !digits.startsWith("7")) return null;
  return `+${digits}`;
}

export function detectContact(raw: string): Contact {
  const text = (raw || "").trim();
  if (!text) return { channel: "invalid", error: "Укажите телефон или почту" };
  if (text.includes("@")) {
    const email = text.toLowerCase();
    if (!EMAIL.test(email)) return { channel: "invalid", error: "Некорректная почта" };
    return { channel: "email", value: email };
  }
  const phone = normalizePhone(text);
  if (!phone) return { channel: "invalid", error: "Укажите телефон в формате +7 или почту" };
  return { channel: "phone", value: phone };
}

export function demoContactError(contact: Contact, demo: boolean): string | null {
  if (!demo || contact.channel === "invalid" || contact.channel === "phone") return null;
  if (!contact.value.endsWith("@demo.superapp")) return DEMO_EMAIL_ERROR;
  return null;
}
