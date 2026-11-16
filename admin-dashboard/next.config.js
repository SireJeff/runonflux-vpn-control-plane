/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  output: 'standalone',

  // API proxy: browser calls /api/v1/* → Next.js server → worker-api:8080
  async rewrites() {
    const proxyTarget = process.env.API_PROXY_URL || 'http://localhost:8080'
    return [
      {
        source: '/api/v1/:path*',
        destination: `${proxyTarget}/api/v1/:path*`,
      },
    ]
  },

  // Environment variables exposed to browser
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080/api/v1',
  },

  // Image optimization
  images: {
    formats: ['image/avif', 'image/webp'],
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'api.qrserver.com',
      },
    ],
  },

  // Performance optimizations
  compiler: {
    removeConsole: process.env.NODE_ENV === 'production',
  },

  // Experimental features
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },
}

module.exports = nextConfig
