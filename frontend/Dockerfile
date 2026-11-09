# ---------------------------------------------------------------
# Multi-stage build:
#   stage 1 (node)  : npm ci + vite build  -> static files in /app/dist
#   stage 2 (nginx) : only the static files + nginx config (~25 MB image)
# Node.js and node_modules never reach the final image.
# Build:  docker build -t devops-ai-frontend:latest ./frontend
# ---------------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run lint && npm run build

FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/nginx-health || exit 1
