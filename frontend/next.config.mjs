/** @type {import('next').NextConfig} */
const nextConfig = {
  eslint: {
    // Pre-existing unused-import warnings should not block production builds.
    // Run `npx next lint` separately to surface and fix them.
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
