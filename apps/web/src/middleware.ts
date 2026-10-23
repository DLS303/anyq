import { NextResponse, type NextRequest } from "next/server";
import { DEMO_MODE } from "./lib/features";
import { REGISTRATION_ENABLED } from "./lib/registration";

const LOCALES = ["ru", "kk"];
/** Finished areas kept out of the release navigation. */
const RELEASE_HIDDEN = ["/catalog", "/plots", "/publish", "/compare", "/control"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/v1") ||
    pathname.startsWith("/health") ||
    pathname.startsWith("/uploads") ||
    pathname.includes(".")
  ) {
    return NextResponse.next();
  }
  if (!REGISTRATION_ENABLED) {
    const bare = pathname.replace(/^\/(ru|kk)(?=\/|$)/, "") || "/";
    const locale = pathname === "/kk" || pathname.startsWith("/kk/") ? "kk" : "ru";
    if (bare === "/register" || bare.startsWith("/register/")) {
      const url = request.nextUrl.clone();
      url.pathname = `/${locale}/login`;
      url.search = "";
      return NextResponse.redirect(url);
    }
    if (bare === "/login" && request.nextUrl.searchParams.get("mode") === "register") {
      const url = request.nextUrl.clone();
      url.pathname = `/${locale}/login`;
      url.searchParams.delete("mode");
      return NextResponse.redirect(url);
    }
  }
  const matched = LOCALES.some((l) => pathname === `/${l}` || pathname.startsWith(`/${l}/`));
  if (!matched) {
    const url = request.nextUrl.clone();
    url.pathname = `/ru${pathname === "/" ? "" : pathname}`;
    return NextResponse.redirect(url);
  }
  const locale = pathname.startsWith("/kk") ? "kk" : "ru";
  const rest = pathname.replace(/^\/(ru|kk)/, "") || "/";
  if (!DEMO_MODE && RELEASE_HIDDEN.some((p) => rest === p || rest.startsWith(`${p}/`))) {
    const url = request.nextUrl.clone();
    url.pathname = `/${locale}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
