import type { NextConfig } from "next";

/**
 * Same-origin backend proxy.
 *
 * Browsers enforce CORS, and the Call-E backend services do not emit CORS
 * headers — so the workspace never calls service ports directly. Instead,
 * client code uses the relative `/backend/*` paths below; the Next.js server
 * (which is not subject to CORS) forwards them to the configured service.
 * No backend change is required for browser access.
 */
const AGENT_API_URL = process.env.AGENT_API_URL ?? "http://localhost:8001";
const KNOWLEDGE_API_URL =
  process.env.KNOWLEDGE_API_URL ?? "http://localhost:8002";
const VOICE_API_URL = process.env.VOICE_API_URL ?? "http://localhost:8003";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/backend/agents/:path*",
        destination: `${AGENT_API_URL}/:path*`,
      },
      {
        source: "/backend/knowledge/:path*",
        destination: `${KNOWLEDGE_API_URL}/:path*`,
      },
      {
        source: "/backend/voice/:path*",
        destination: `${VOICE_API_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
