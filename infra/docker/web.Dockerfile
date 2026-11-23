# The Next.js console, production build. Build context is the repo root. Multi-arch (node:22 is
# published for amd64 and arm64). The browser only talks to this server; it proxies /api/gauntlet
# to GAUNTLET_API_URL at request time, so one image serves any deployment.
FROM node:22-bookworm-slim AS deps
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH CI=1
RUN corepack enable
WORKDIR /repo
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN --mount=type=cache,target=/pnpm/store pnpm install --frozen-lockfile --filter web...

FROM deps AS build
ENV NEXT_TELEMETRY_DISABLED=1
COPY apps/web apps/web
RUN pnpm --filter web build

FROM node:22-bookworm-slim AS web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN useradd --uid 10001 --create-home gauntlet
WORKDIR /app
COPY --from=build --chown=gauntlet:gauntlet /repo/apps/web/.next/standalone ./
COPY --from=build --chown=gauntlet:gauntlet /repo/apps/web/.next/static apps/web/.next/static
COPY --from=build --chown=gauntlet:gauntlet /repo/apps/web/public apps/web/public
USER gauntlet
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
