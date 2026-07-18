import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Feed and ledger are read at runtime from the data branch CDN; nothing to
  // pre-render from the Python side. Keep the default Node.js runtime so the
  // chat route can run without Edge constraints (per Vercel guidance).
};

export default nextConfig;
