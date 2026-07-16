import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  typedRoutes: true,
  // S10PAT02: the cloud build is a fully static export served by the
  // codex-eei Worker's assets binding; EEI_CLOUD_EXPORT=1 keeps local dev
  // and the CI dev-server E2E flow on the default server runtime.
  ...(process.env.EEI_CLOUD_EXPORT === "1" ? { output: "export" as const } : {})
};

export default nextConfig;
