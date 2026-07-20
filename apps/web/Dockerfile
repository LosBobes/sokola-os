# Production image for the SOKOLA web app.
#
# Multi-stage: build the static SPA with Vite, then serve it with nginx. nginx
# also reverse-proxies /api/ to the `api` service on the internal Compose
# network, so the browser only ever talks to one origin (this container) and
# Caddy on the host only needs to know about one upstream port. Mirrors the
# same-origin /api convention used by apps/web/vite.config.ts in dev.

FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD wget -qO- http://localhost/ >/dev/null || exit 1
