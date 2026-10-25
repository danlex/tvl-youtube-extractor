/** @type {import('next').NextConfig} */
// Static export so FastAPI can serve the built UI as a single local app.
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
