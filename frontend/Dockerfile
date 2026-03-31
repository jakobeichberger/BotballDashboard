FROM node:20-alpine AS builder

ENV PNPM_HOME=/usr/local/bin
RUN corepack enable && corepack prepare pnpm@10.29.3 --activate

WORKDIR /app
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile --ignore-scripts
# esbuild needs its post-install script to download the native binary;
# run it directly with Node to avoid pnpm's stream handling in LXC/Docker
RUN node node_modules/.pnpm/esbuild@*/node_modules/esbuild/install.js

COPY . .
ARG VITE_API_URL=/api
ARG VITE_VAPID_PUBLIC_KEY=
ENV VITE_API_URL=$VITE_API_URL \
    VITE_VAPID_PUBLIC_KEY=$VITE_VAPID_PUBLIC_KEY
RUN pnpm build

# ── Serve with nginx ──────────────────────────────────────────
FROM nginx:alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
