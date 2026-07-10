import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

// 1. Removed "/dashboard" from here. The dashboard is strictly a private, protected route!
const publicRoutes = ["/sign-in", "/sign-up", "/forgot-password", "/"]

// Notice the function is now exported as 'proxy'
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl
  
  // 2. Updated to check for your specific JWT cookie name
  const hasToken = request.cookies.has("calle-auth-token") 
  const isPublicRoute = publicRoutes.includes(pathname)

  // If they don't have a token and try to access a private route -> send to sign-in
  if (!hasToken && !isPublicRoute) {
    return NextResponse.redirect(new URL("/sign-in", request.url))
  }

  // If they DO have a token, and try to access a public route (like sign-in or sign-up) -> send to dashboard
  if (hasToken && isPublicRoute) {
    return NextResponse.redirect(new URL("/dashboard", request.url))
  }

  return NextResponse.next()
}

// This tells Next.js EXACTLY which routes to run this proxy on.
// We exclude static files, images, and internal build files to prevent infinite loops.
export const config = {
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico).*)",
  ],
}