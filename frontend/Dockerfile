# Runs the same Vite dev server used for local development (hot-reload,
# unminified) -- not a production static build. Fine for an internal/LAN
# deployment; if this needs to be public-facing later, switch to `vite
# build` + a static file server instead.
#
# Build: docker build -t yeastpanoptic-frontend frontend
# (normally built/run via docker-compose.yml instead -- see repo root)
FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

CMD ["npx", "vite", "--host", "0.0.0.0"]
