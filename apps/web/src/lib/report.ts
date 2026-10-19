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
