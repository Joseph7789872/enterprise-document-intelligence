# syntax=docker/dockerfile:1
# Production image for the Next.js frontend. Multi-stage build → small standalone runtime
# served by a non-root user. Requires `output: "standalone"` in next.config.mjs.

# ── Dependencies ─────────────────────────────────────────────────────────────────────
FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# ── Build ────────────────────────────────────────────────────────────────────────────
FROM node:20-slim AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* must be present at build time (baked into the client bundle).
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN npm run build

# ── Runtime ──────────────────────────────────────────────────────────────────────────
FROM node:20-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000

# Copy the standalone server + static assets only.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

# node:20-slim ships a non-root `node` user.
USER node

EXPOSE 3000
CMD ["node", "server.js"]
