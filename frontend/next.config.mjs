/** @type {import('next').NextConfig} */
const backend = process.env.PROOFBOX_API_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // In production Caddy sends /api straight to FastAPI. This rewrite is for local dev.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
