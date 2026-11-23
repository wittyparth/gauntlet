import type { NextConfig } from "next";

// `standalone` emits a self-contained server for the production image (infra/docker/web.Dockerfile).
const nextConfig: NextConfig = { output: "standalone" };

export default nextConfig;
