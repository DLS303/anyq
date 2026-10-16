import { NextResponse, type NextRequest } from "next/server";

const LOCALES = ["ru", "kk"];
const LAND = ["/catalog", "/plots", "/publish", "/compare", "/moderation"];

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
  if (LAND.some((p) => rest === p || rest.startsWith(`${p}/`))) {
    const url = request.nextUrl.clone();
    url.pathname = `/${locale}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
