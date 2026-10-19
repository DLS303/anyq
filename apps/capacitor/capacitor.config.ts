import type { CapacitorConfig } from "@capacitor/cli";

/**
 * Server origin baked into the native shell at `cap sync`.
 * The production domain is not purchased yet. `https://app.anyq.example`
 * is an RFC 2606 placeholder, not a live host. Set ANYQ_APP_URL to the
 * real origin, a staging origin, or a local address before syncing.
 */
export const DEFAULT_APP_URL = "https://app.anyq.example";

export function resolveAppUrl(raw = process.env.ANYQ_APP_URL): string {
  const value = (raw || DEFAULT_APP_URL).trim();
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") return DEFAULT_APP_URL;
    return url.toString().replace(/\/$/, "");
  } catch {
    return DEFAULT_APP_URL;
  }
}

const serverUrl = resolveAppUrl();
const hostname = new URL(serverUrl).hostname;
const cleartext = serverUrl.startsWith("http://");

const config: CapacitorConfig = {
  appId: "kz.dls.anyq",
  appName: "Анык",
  webDir: "www",
  server: {
    url: serverUrl,
    cleartext,
    androidScheme: "https",
    allowNavigation: [hostname, "localhost", "10.0.2.2"],
    errorPath: "offline.html",
  },
  android: {
    allowMixedContent: cleartext,
    captureInput: true,
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 1200,
      launchAutoHide: true,
      backgroundColor: "#2F5B8A",
      androidScaleType: "CENTER_INSIDE",
      showSpinner: false,
      splashFullScreen: true,
    },
    StatusBar: {
      overlaysWebView: true,
      style: "DARK",
      backgroundColor: "#EFE8DE",
    },
  },
};

export default config;
