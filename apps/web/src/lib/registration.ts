/** Public sign-up. Off unless NEXT_PUBLIC_REGISTRATION_ENABLED is exactly "1". */
export const REGISTRATION_ENABLED = process.env.NEXT_PUBLIC_REGISTRATION_ENABLED === "1";

export function loginInitialMode(
  queryMode: string | undefined,
  pilotMode: boolean,
  enabled = REGISTRATION_ENABLED,
): "login" | "register" {
  if (!enabled || pilotMode || queryMode === "login") return "login";
  return "register";
}

export function registerHref(locale: string, enabled = REGISTRATION_ENABLED): string {
  return enabled ? `/${locale}/login?mode=register` : `/${locale}/login`;
}

/** Path without a locale prefix. Header links add the locale themselves. */
export function guestEntryPath(pilotMode: boolean, enabled = REGISTRATION_ENABLED): string {
  return enabled && !pilotMode ? "/login?mode=register" : "/login";
}
