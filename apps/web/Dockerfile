FROM node:20-alpine AS base

# ─── Dependencies ────────────────────────────────────────────────
FROM base AS deps
WORKDIR /app
RUN apk add --no-cache libc6-compat
COPY package.json pnpm-lock.yaml* ./
COPY ../../package.json ../../pnpm-workspace.yaml ../../turbo.json /tmp/workspace/
COPY ../../packages/shared/package.json /tmp/workspace/packages/shared/
RUN corepack enable && pnpm install --frozen-lockfile

# ─── Build ───────────────────────────────────────────────────────
FROM base AS build
WORKDIR /app
RUN corepack enable
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

# ─── Runtime ────────────────────────────────────────────────────
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs
COPY --from=build /app/public ./public
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
