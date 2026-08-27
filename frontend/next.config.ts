import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The project already has CLAUDE.md at its root; a second, generated one
  // inside frontend/ would compete with it.
  agentRules: false,
  /* config options here */
};

export default nextConfig;
