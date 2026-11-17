import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@rentfit/ui"],
  eslint: { ignoreDuringBuilds: true }, // linting runs as its own task
  poweredByHeader: false,
};

export default nextConfig;
