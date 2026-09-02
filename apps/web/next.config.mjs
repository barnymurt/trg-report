/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@trg/shared"],
  // Static export for Cloudflare Pages. The PWA talks to the agent backend
  // over the network (NEXT_PUBLIC_API_URL); no server-side rendering needed.
  output: "export",
  images: {
    unoptimized: true,
  },
  experimental: {
    typedRoutes: true,
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "microphone=(self), camera=(self), geolocation=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
