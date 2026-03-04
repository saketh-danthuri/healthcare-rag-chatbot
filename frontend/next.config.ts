import type { NextConfig } from "next";

const isProd = process.env.NODE_ENV === "production";

const nextConfig: NextConfig = isProd
  ? {
      // Production: Static export for Azure Static Web Apps
      output: "export",
    }
  : {
      // Development: Proxy API calls to local backend
      async rewrites() {
        return [
          {
            source: "/api/:path*",
            destination: "http://localhost:8000/api/:path*",
          },
        ];
      },
    };

export default nextConfig;
