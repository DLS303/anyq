import type { Msg } from "@/i18n/messages";

export function weatherLabel(code: string, m: Msg) {
  switch (code) {
    case "clear":
      return m.weatherClear;
    case "cloud":
      return m.weatherCloud;
    case "rain":
      return m.weatherRain;
    case "snow":
      return m.weatherSnow;
    case "wind":
      return m.weatherWind;
    default:
      return code;
  }
}

export function statusLabel(code: string, m: Msg) {
  switch (code) {
    case "open":
      return m.statusOpen;
    case "answered":
      return m.statusAnswered;
    case "closed":
      return m.statusClosed;
    case "ready":
      return m.statusReady;
    case "pending":
      return m.statusPending;
    case "fail":
      return m.statusFail;
    case "pass":
      return m.statusPass;
    case "na":
      return m.statusNa;
    case "draft":
      return m.statusDraft;
    case "submitted":
      return m.statusSubmitted;
    case "approved":
      return m.statusApproved;
    case "rejected":
      return m.statusRejected;
    case "low":
      return m.statusLow;
    case "medium":
      return m.statusMedium;
    case "high":
      return m.statusHigh;
    case "not_started":
      return m.statusNotStarted;
    case "in_progress":
      return m.statusInProgress;
    case "done":
      return m.statusDone;
    case "blocked":
      return m.statusBlocked;
    default:
      return code;
  }
}

export const SITE_ROLES = ["buyer", "contractor", "supervisor", "architect", "surveyor", "supplier", "foreman", "procurement", "customer"] as const;

export function siteRoleLabel(role: string, m: Msg) {
  switch (role) {
    case "architect":
      return m.roleArchitect;
    case "surveyor":
      return m.roleSurveyor;
    case "foreman":
      return m.roleForeman;
    case "procurement":
      return m.roleProcurement;
    case "customer":
      return m.roleCustomer;
    default:
      return roleLabel(role, m);
  }
}

export function roleLabel(role: string, m: Msg) {
  switch (role) {
    case "buyer":
      return m.roleBuyer;
    case "owner":
      return m.roleOwner;
    case "moderator":
      return m.roleModerator;
    case "admin":
      return m.roleAdmin;
    case "guest":
      return m.roleGuest;
    case "specialist":
      return m.specialist;
    case "contractor":
      return m.contractor;
    case "supplier":
      return m.supplier;
    case "supervisor":
      return m.supervisor;
    default:
      return role ? m.roleMember : "";
  }
}

export function shareText(m: Msg, day: string, url: string) {
  return m.reportShareText.replace("{date}", day).replace("{url}", url);
}

export function todayAlmaty() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Almaty" }).format(new Date());
}
