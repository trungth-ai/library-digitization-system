/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output cho Docker (image nhỏ, chạy `node server.js`)
  output: "standalone",

  // Ảnh không tối ưu (không cần server tối ưu ảnh; tránh phụ thuộc domain khi air-gapped)
  images: {
    unoptimized: true,
  },

  env: {
    NEXT_PUBLIC_DSPACE_URL: process.env.NEXT_PUBLIC_DSPACE_URL,
    NEXT_PUBLIC_OCR_API_URL: process.env.NEXT_PUBLIC_OCR_API_URL,
    NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL,
  },
};

export default nextConfig;
