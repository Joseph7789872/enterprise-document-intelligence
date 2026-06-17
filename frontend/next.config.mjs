/** @type {import('next').NextConfig} */
const nextConfig = {
  // Emit a self-contained server bundle for a small, non-root production image.
  output: "standalone",
  reactStrictMode: true,
};

export default nextConfig;
