# syntax=docker/dockerfile:1

FROM node:20-alpine AS base
WORKDIR /app

# ── Install dependencies ──────────────────────────────────────────────────────
FROM base AS deps
COPY package*.json .
RUN npm ci

# ── Build ─────────────────────────────────────────────────────────────────────
FROM deps AS builder
COPY . .
RUN npm run build

# ── Serve (for local preview — Cloudflare Pages serves in production) ─────────
FROM node:20-alpine AS runner
WORKDIR /app
RUN addgroup --system nextgroup && adduser --system --ingroup nextgroup nextuser

COPY --from=builder /app/out ./out

RUN npm install -g serve
USER nextuser

EXPOSE 3000
CMD ["serve", "-s", "out", "-l", "3000"]
