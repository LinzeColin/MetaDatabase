import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  typedRoutes: true,
  // The cloud build is a fully static export. Production serves it from the
  // self-hosted universe container (apps/universe/deploy/Dockerfile builds it
  // with NEXT_PUBLIC_EEI_API_BASE_URL=same-origin); EEI_CLOUD_EXPORT=1 keeps
  // local dev and the CI dev-server E2E flow on the default server runtime.
  ...(process.env.EEI_CLOUD_EXPORT === "1" ? { output: "export" as const } : {})
};

export default nextConfig;
