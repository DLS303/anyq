import { PILOT_MODE } from "@/lib/pilot";

const ENABLED = new Set(["1", "true", "yes", "on"]);

/** Public sign-up. Off unless the value is 1, true, yes, or on. */
export function registrationEnabled(raw: string | undefined = process.env.NEXT_PUBLIC_REGISTRATION_ENABLED): boolean {
  return ENABLED.has((raw ?? "").trim().toLowerCase());
}

export const REGISTRATION_ENABLED = registrationEnabled();

export function publicRegistrationOpen(options?: { pilot?: boolean; enabled?: boolean }): boolean {
  const enabled = options?.enabled ?? REGISTRATION_ENABLED;
  const pilot = options?.pilot ?? PILOT_MODE;
  return enabled && !pilot;
}

/** Login URL that opens sign-up. Null means the control stays hidden. */
export function registerLink(locale: string, options?: { pilot?: boolean; enabled?: boolean }): string | null {
  if (!publicRegistrationOpen(options)) return null;
  return `/${locale}/login?mode=register`;
}
