import { NextResponse, type NextRequest } from "next/server";
import { DEMO_MODE, referrerPolicyFor } from "./lib/features";

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
  const response = NextResponse.next();
  const tokenPage = /^\/(ru|kk)\/r\/(rfi|material)\//.test(pathname);
  const policy = tokenPage ? "no-referrer" : referrerPolicyFor(pathname) || "strict-origin-when-cross-origin";
  response.headers.set("Referrer-Policy", policy);
  if (tokenPage) response.headers.set("X-Robots-Tag", "noindex, nofollow");
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
