import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

/**
 * Decode JWT payload without verification (backend handles verification).
 * Extracts the role claim for route protection.
 */
function getRoleFromToken(token: string): string | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.role || payload.sub ? (payload.role as string) : null
  } catch {
    return null
  }
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl
  const hostname = request.headers.get('host')?.split(':')[0] || ''
  const isUserPortal = hostname === 'panel.operator5.example.invalid'

  // ---- USER PORTAL: restrict to /user/* and /api/v1/* only ----
  if (isUserPortal) {
    if (pathname.startsWith('/dashboard') || pathname.startsWith('/super')) {
      return NextResponse.rewrite(new URL('/404', request.url))
    }
    if (pathname === '/login' || pathname === '/register') {
      return NextResponse.rewrite(new URL('/404', request.url))
    }
    if (pathname === '/') {
      return NextResponse.redirect(new URL('/user/login', request.url))
    }
  }

  // Role-specific login pages are public
  if (pathname === '/super/login' || pathname === '/user/login') {
    return NextResponse.next()
  }

  // Public routes that do not require authentication
  const publicPaths = ['/login', '/register']
  if (publicPaths.some((p) => pathname === p)) {
    return NextResponse.next()
  }

  // Read token from cookie (set by useAuth on login)
  const token = request.cookies.get('auth_token')?.value

  // No token -> redirect to login
  if (!token) {
    const loginPath = isUserPortal ? '/user/login' : '/login'
    return NextResponse.redirect(new URL(loginPath, request.url))
  }

  const role = getRoleFromToken(token)

  // Super admin routes
  if (pathname.startsWith('/super')) {
    if (role !== 'super_admin') {
      return NextResponse.redirect(new URL('/login', request.url))
    }
  }

  // Admin dashboard routes (excluding super admin routes)
  if (pathname.startsWith('/dashboard')) {
    if (role !== 'super_admin' && role !== 'admin') {
      return NextResponse.redirect(new URL('/login', request.url))
    }
  }

  // End user routes
  if (pathname.startsWith('/user')) {
    if (role !== 'end_user' && role !== 'admin' && role !== 'super_admin') {
      return NextResponse.redirect(new URL('/user/login', request.url))
    }
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    '/dashboard/:path*',
    '/super/:path*',
    '/user/:path*',
    '/login',
    '/register',
    '/super/login',
    '/user/login',
    '/',
  ],
}
