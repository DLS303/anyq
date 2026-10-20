# Production image. Build context is the repository root (npm workspaces).
#   docker build -f apps/web/Dockerfile .

FROM node:20-alpine AS base
RUN apk add --no-cache libc6-compat
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

FROM base AS deps
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
RUN npm ci

FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY apps/web ./apps/web
ARG NEXT_PUBLIC_PILOT_MODE=1
ARG INTERNAL_API_URL=http://api:8010
ENV NEXT_PUBLIC_PILOT_MODE=$NEXT_PUBLIC_PILOT_MODE
ENV INTERNAL_API_URL=$INTERNAL_API_URL
ENV NODE_OPTIONS=--max-old-space-size=2048
WORKDIR /app/apps/web
RUN npm run build \
    && if [ ! -f .next/standalone/apps/web/server.js ]; then \
         echo "standalone server.js layout:" >&2; \
         find .next/standalone -name server.js -print >&2; \
         exit 1; \
       fi

FROM base AS runner
ENV NODE_ENV=production
RUN addgroup -g 1001 -S nodejs \
    && adduser -S -u 1001 -G nodejs nextjs
WORKDIR /app
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/public ./apps/web/public
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/content ./apps/web/content
# Legal pages read files from process.cwd()/content/legal. The server process
# uses /app as its working directory.
RUN ln -sfn apps/web/content /app/content \
    && chown -h nextjs:nodejs /app/content
COPY --chown=nextjs:nodejs apps/web/docker-entrypoint.sh /usr/local/bin/anyq-web-entrypoint
RUN chmod 755 /usr/local/bin/anyq-web-entrypoint
USER nextjs
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD wget -q -O /dev/null http://127.0.0.1:3000/healthz || exit 1
ENTRYPOINT ["anyq-web-entrypoint"]
