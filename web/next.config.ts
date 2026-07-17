import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produce a self-contained server bundle for the Docker image
  // (no node_modules needed at runtime).
  output: "standalone",
};

export default nextConfig;
