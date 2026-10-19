export const XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
export const PDF_MIME = "application/pdf";

type PluginProxy = {
  [method: string]: (...args: unknown[]) => Promise<unknown> & { remove?: () => Promise<void> };
};

type CapacitorBridge = {
  isNativePlatform?: () => boolean;
  registerPlugin?: (name: string) => PluginProxy;
};

export type AnchorPlan =
  | { type: "ignore" }
  | { type: "download"; filename: string; href: string }
  | { type: "whatsapp"; text: string; href: string }
  | { type: "external"; href: string };

type NativePosition = {
  timestamp?: number;
  coords?: {
    latitude?: number;
    longitude?: number;
    accuracy?: number;
    altitude?: number | null;
    altitudeAccuracy?: number | null;
    heading?: number | null;
    speed?: number | null;
  };
};

let shellReady = false;
let bypassClick = false;
const watchTimers = new Map<number, number>();

export function capacitorBridge(): CapacitorBridge | null {
  if (typeof window === "undefined") return null;
  const cap = (window as Window & { Capacitor?: CapacitorBridge }).Capacitor;
  if (!cap?.isNativePlatform?.()) return null;
  return cap;
}

export function isNativeApp() {
  return capacitorBridge() !== null;
}

export function safeFilename(name: string) {
  const cleaned = name.replace(/\.\./g, "_").replace(/[\\/]+/g, "_").trim();
  return cleaned || "download";
}

export function wantsNativeCamera(accept: string, capture: string | null) {
  const kind = accept.toLowerCase();
  if (kind.includes("image")) return true;
  return Boolean(capture);
}

export function classifyAnchor(href: string, origin: string, download: string | null): AnchorPlan {
  let url: URL;
  try {
    url = new URL(href, origin);
  } catch {
    return { type: "ignore" };
  }
  if (download !== null) {
    const filename = safeFilename(download || fileNameFromUrl(url));
    return { type: "download", filename, href: url.toString() };
  }
  if (url.origin === origin) return { type: "ignore" };
  if (url.protocol !== "http:" && url.protocol !== "https:") return { type: "ignore" };
  const host = url.hostname.toLowerCase();
  if (host === "wa.me" || host === "api.whatsapp.com" || host.endsWith(".whatsapp.com")) {
    return { type: "whatsapp", text: url.searchParams.get("text") || url.toString(), href: url.toString() };
  }
  return { type: "external", href: url.toString() };
}

function fileNameFromUrl(url: URL) {
  const last = decodeURIComponent(url.pathname.split("/").pop() || "");
  return last || "download";
}

function plugin(name: string): PluginProxy | null {
  const bridge = capacitorBridge();
  if (!bridge?.registerPlugin) return null;
  return bridge.registerPlugin(name);
}

async function blobToBase64(blob: Blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  const size = 0x2000;
  for (let index = 0; index < bytes.length; index += size) {
    binary += String.fromCharCode(...bytes.subarray(index, index + size));
  }
  return btoa(binary);
}

export function bytesToBlob(data: unknown, mime: string) {
  let part: BlobPart = "";
  if (data instanceof ArrayBuffer) part = data;
  else if (data instanceof Uint8Array) part = new Uint8Array(data) as BlobPart;
  else if (Array.isArray(data) && data.every((item) => typeof item === "number")) part = Uint8Array.from(data) as BlobPart;
  else if (typeof data === "string") part = data;
  return new Blob([part], { type: mime });
}

export async function saveBlobDownload(filename: string, blob: Blob) {
  const native = plugin("AnyqNative");
  if (!native) return false;
  try {
    await native.saveFile({
      filename: safeFilename(filename),
      data: await blobToBase64(blob),
      mime: blob.type || "application/octet-stream",
    });
    return true;
  } catch {
    return false;
  }
}

export async function captureNativePhoto(): Promise<File | "cancel" | null> {
  const camera = plugin("Camera");
  if (!camera?.getPhoto) return null;
  try {
    const photo = (await camera.getPhoto({
      quality: 80,
      allowEditing: false,
      resultType: "base64",
      source: "CAMERA",
      correctOrientation: true,
      width: 1600,
      saveToGallery: false,
    })) as { base64String?: string; format?: string };
    if (!photo.base64String) return null;
    const binary = atob(photo.base64String);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    const png = photo.format === "png";
    return new File([bytes], png ? "anyq-photo.png" : "anyq-photo.jpg", { type: png ? "image/png" : "image/jpeg" });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error || "");
    if (/cancel/i.test(message)) return "cancel";
    return null;
  }
}

async function openExternal(url: string) {
  const native = plugin("AnyqNative");
  if (!native) return;
  try {
    await native.openExternal({ url });
  } catch {
    window.location.assign(url);
  }
}

async function shareWhatsApp(text: string, href: string) {
  const share = plugin("Share");
  if (!share) {
    await openExternal(href);
    return;
  }
  try {
    await share.share({ title: "Анык", text, dialogTitle: "WhatsApp" });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error || "");
    if (/cancel/i.test(message)) return;
    await openExternal(href);
  }
}

async function saveFromHref(filename: string, href: string) {
  try {
    const response = await fetch(href);
    if (!response.ok) return false;
    return saveBlobDownload(filename, await response.blob());
  } catch {
    return false;
  }
}

async function attachPhoto(input: HTMLInputElement) {
  const photo = await captureNativePhoto();
  if (photo === "cancel") return;
  if (photo && typeof DataTransfer !== "undefined") {
    const transfer = new DataTransfer();
    transfer.items.add(photo);
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    return;
  }
  bypassClick = true;
  input.click();
  bypassClick = false;
}

function onNativeClick(event: MouseEvent) {
  if (bypassClick || !isNativeApp()) return;
  const target = event.target;
  if (!(target instanceof Element)) return;
  const input = target.closest("input");
  if (input instanceof HTMLInputElement && input.type === "file") {
    if (!wantsNativeCamera(input.accept || "", input.getAttribute("capture"))) return;
    event.preventDefault();
    event.stopPropagation();
    void attachPhoto(input);
    return;
  }
  const anchor = target.closest("a");
  if (!(anchor instanceof HTMLAnchorElement) || !anchor.href) return;
  const plan = classifyAnchor(anchor.href, window.location.origin, anchor.getAttribute("download"));
  if (plan.type === "ignore") return;
  event.preventDefault();
  event.stopPropagation();
  if (plan.type === "download") {
    void saveFromHref(plan.filename, plan.href).then((saved) => {
      if (saved) return;
      bypassClick = true;
      anchor.click();
      bypassClick = false;
    });
    return;
  }
  if (plan.type === "whatsapp") {
    void shareWhatsApp(plan.text, plan.href);
    return;
  }
  void openExternal(plan.href);
}

function geoError(code: number, message: string): GeolocationPositionError {
  return {
    code,
    message,
    PERMISSION_DENIED: 1,
    POSITION_UNAVAILABLE: 2,
    TIMEOUT: 3,
  } as GeolocationPositionError;
}

function geoPosition(raw: NativePosition): GeolocationPosition {
  const coords = raw.coords || {};
  return {
    timestamp: raw.timestamp || Date.now(),
    coords: {
      latitude: Number(coords.latitude || 0),
      longitude: Number(coords.longitude || 0),
      accuracy: Number(coords.accuracy || 0),
      altitude: coords.altitude ?? null,
      altitudeAccuracy: coords.altitudeAccuracy ?? null,
      heading: coords.heading ?? null,
      speed: coords.speed ?? null,
      toJSON() {
        return this;
      },
    },
    toJSON() {
      return this;
    },
  } as GeolocationPosition;
}

function installGeolocationBridge() {
  const geo = plugin("Geolocation");
  if (!geo || !navigator.geolocation) return;
  const read = (options?: PositionOptions) =>
    geo.getCurrentPosition({
      enableHighAccuracy: Boolean(options?.enableHighAccuracy),
      timeout: options?.timeout ?? 10000,
      maximumAge: options?.maximumAge ?? 0,
    }) as Promise<NativePosition>;
  const wrapped: Geolocation = {
    getCurrentPosition(success, error, options) {
      void read(options)
        .then((position) => success(geoPosition(position)))
        .catch((reason: unknown) => {
          const message = reason instanceof Error ? reason.message : "Геолокация недоступна";
          error?.(geoError(1, message));
        });
    },
    watchPosition(success, error, options) {
      const id = window.setInterval(() => {
        this.getCurrentPosition(success, error, options);
      }, Math.max(5000, options?.timeout || 5000));
      watchTimers.set(id, id);
      this.getCurrentPosition(success, error, options);
      return id;
    },
    clearWatch(id) {
      const timer = watchTimers.get(id);
      if (timer !== undefined) window.clearInterval(timer);
      watchTimers.delete(id);
    },
  };
  Object.defineProperty(navigator, "geolocation", { configurable: true, value: wrapped });
}

function installMicrophoneBridge() {
  const media = navigator.mediaDevices;
  const native = plugin("AnyqNative");
  if (!media?.getUserMedia || !native) return;
  const original = media.getUserMedia.bind(media);
  media.getUserMedia = async (constraints) => {
    if (constraints && typeof constraints === "object" && "audio" in constraints && constraints.audio) {
      try {
        await native.requestMicrophone();
      } catch {
        /* the WebView permission prompt still runs */
      }
    }
    return original(constraints);
  };
}

function installWindowOpen() {
  const original = window.open.bind(window);
  window.open = (url?: string | URL, target?: string, features?: string) => {
    const raw = url == null ? "" : String(url);
    if (raw.startsWith("http://") || raw.startsWith("https://")) {
      try {
        const parsed = new URL(raw);
        if (parsed.origin !== window.location.origin) {
          const plan = classifyAnchor(parsed.toString(), window.location.origin, null);
          if (plan.type === "whatsapp") void shareWhatsApp(plan.text, plan.href);
          else void openExternal(parsed.toString());
          return null;
        }
      } catch {
        /* keep the original window.open */
      }
    }
    return original(url, target, features);
  };
}

async function installChrome() {
  const app = plugin("App");
  if (app) {
    await app.addListener("backButton", (event: unknown) => {
      const canGoBack = Boolean((event as { canGoBack?: boolean } | null)?.canGoBack);
      if (canGoBack) window.history.back();
      else void app.minimizeApp();
    });
  }
  const status = plugin("StatusBar");
  if (status) {
    try {
      await status.setOverlaysWebView({ overlay: true });
      await status.setStyle({ style: "DARK" });
      await status.setBackgroundColor({ color: "#EFE8DE" });
    } catch {
      /* Android 15 ignores some status-bar calls */
    }
  }
  const splash = plugin("SplashScreen");
  if (splash) {
    try {
      await splash.hide();
    } catch {
      /* splash already hidden */
    }
  }
}

export async function watchNativeNetwork(onOffline: (offline: boolean) => void) {
  const network = plugin("Network");
  const apply = (connected: boolean | undefined) => onOffline(connected === false);
  window.addEventListener("offline", () => onOffline(true));
  window.addEventListener("online", () => onOffline(false));
  if (!network) {
    apply(navigator.onLine);
    return;
  }
  try {
    const status = (await network.getStatus()) as { connected?: boolean };
    apply(status.connected);
    await network.addListener("networkStatusChange", (next: unknown) => {
      apply((next as { connected?: boolean } | null)?.connected);
    });
  } catch {
    apply(navigator.onLine);
  }
}

export function registerWebServiceWorker() {
  if (process.env.NODE_ENV !== "production") return;
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  if (isNativeApp()) return;
  void navigator.serviceWorker.register("/sw.js");
}

export function initNativeShell() {
  if (shellReady || !isNativeApp()) return;
  shellReady = true;
  document.addEventListener("click", onNativeClick, true);
  installGeolocationBridge();
  installMicrophoneBridge();
  installWindowOpen();
  void installChrome();
}
