# =============================================================================
# Multi-stage build for Next.js with Development & Production modes
# =============================================================================

# Base image
FROM node:20-alpine AS base
RUN apk add --no-cache libc6-compat
WORKDIR /app

# =============================================================================
# Stage 1: Dependencies
# =============================================================================
FROM base AS deps
WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm ci

# =============================================================================
# Stage 2: Development (Hot Reload)
# =============================================================================
FROM base AS development
WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install ALL dependencies (including dev)
RUN npm install

# Copy source code
COPY . .

# Expose port
EXPOSE 3000

ENV NODE_ENV=development
ENV NEXT_TELEMETRY_DISABLED=1

# Start development server
CMD ["npm", "run", "dev"]

# =============================================================================
# Stage 3: Builder (Build Production Assets)
# =============================================================================
FROM base AS builder
WORKDIR /app

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy all source files
COPY . .



# Build Next.js application
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

# ⚠️ NEXT_PUBLIC_* được NHÚNG VÀO BUNDLE lúc BUILD, không đọc lúc chạy. Đặt chúng ở `environment`
# của docker-compose là VÔ TÁC DỤNG với mã phía client (chỉ server-side thấy được). Vì vậy phải
# nhận qua build-arg — nếu không, trình duyệt sẽ gọi vào URL sai và các lời gọi client (SSE, fetch
# trực tiếp) thất bại im lặng.
#
# Giá trị phải là URL mà TRÌNH DUYỆT truy cập được (qua Caddy), không phải tên service Docker.
ARG NEXT_PUBLIC_OCR_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_DSPACE_URL=https://lib.hpu.edu.vn
ARG NEXT_PUBLIC_SITE_URL=http://localhost:3000
ENV NEXT_PUBLIC_OCR_API_URL=${NEXT_PUBLIC_OCR_API_URL}
ENV NEXT_PUBLIC_DSPACE_URL=${NEXT_PUBLIC_DSPACE_URL}
ENV NEXT_PUBLIC_SITE_URL=${NEXT_PUBLIC_SITE_URL}

RUN npm run build

# =============================================================================
# Stage 4: Production Runner (Minimal Runtime)
# =============================================================================
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy necessary files from builder
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static


# Set correct permissions
RUN chown -R nextjs:nodejs /app

# Switch to non-root user
USER nextjs

# Expose port
EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/api/health', (r) => {process.exit(r.statusCode === 200 ? 0 : 1)})"

# Start production server
CMD ["node", "server.js"]