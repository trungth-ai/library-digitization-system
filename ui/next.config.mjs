/** @type {import('next').NextConfig} */
const nextConfig = {
  // ✨ Enable standalone output for Docker (smaller image)
  output: 'standalone',
  
  // Disable telemetry in production
  experimental: {
    instrumentationHook: false,
  },
  
  // Image optimization settings
  images: {
    domains: ['lib.hpu.edu.vn'], // Add your DSpace domain if using Next/Image
    unoptimized: true, // Disable optimization in Docker (can be removed if needed)
  },
  
  // Environment variables validation
  env: {
    NEXT_PUBLIC_DSPACE_URL: process.env.NEXT_PUBLIC_DSPACE_URL,
    NEXT_PUBLIC_OCR_API_URL: process.env.NEXT_PUBLIC_OCR_API_URL,
    NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL,
  },
  
};

export default nextConfig;