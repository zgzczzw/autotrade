import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/register"];
const EXEMPT_PREFIXES = ["/api/auth", "/_next", "/favicon.ico"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Exempt static assets, Next.js internals, and auth API
  if (EXEMPT_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return NextResponse.next();
  }

  const hasSession = request.cookies.has("session");

  // Already logged in → redirect away from login/register
  if (hasSession && PUBLIC_PATHS.includes(pathname)) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  // Not logged in → redirect to login
  if (!hasSession && !PUBLIC_PATHS.includes(pathname)) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  // Match all routes except static files
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
