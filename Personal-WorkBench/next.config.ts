import type { NextConfig } from "next";

const RETIRED_WORKBENCH_HOST = "huchuliang-workbench.linzezhang35.chatgpt.site";

const nextConfig: NextConfig = {
  serverExternalPackages: ["better-sqlite3"],
  output: "standalone",
  // Keep the local production-equivalent harness aligned with the exact
  // retired host that the deployed CSRF policy accepts.
  allowedDevOrigins: [RETIRED_WORKBENCH_HOST],
  experimental: {
    serverActions: {
      // The retiring hostname may submit only the bounded, browser-local
      // history handoff to the canonical host. Vinext expects hostnames here,
      // and the receiving route independently checks this exact Origin.
      allowedOrigins: [RETIRED_WORKBENCH_HOST],
      // The transfer parser retains a much smaller anonymous payload bound;
      // this ceiling includes multipart and UTF-8 form overhead.
      bodySizeLimit: "8mb",
    },
  },
};

export default nextConfig;
