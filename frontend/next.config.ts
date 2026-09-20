import type { NextConfig } from 'next';
import { PHASE_DEVELOPMENT_SERVER } from 'next/constants';

const nextConfig = (phase: string): NextConfig => ({
  // Builds must not overwrite the assets served by an open dev session.
  distDir: phase === PHASE_DEVELOPMENT_SERVER ? '.next' : '.next-build',
  eslint: {
    ignoreDuringBuilds: true,
  },
});

export default nextConfig;
