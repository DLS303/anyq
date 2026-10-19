export function toast(message: string) {
  if (typeof window === "undefined" || !message) return;
  window.dispatchEvent(new CustomEvent("anyq-toast", { detail: { message } }));
}
