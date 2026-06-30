# Frontend image: build the static bundle with Node, serve it with nginx.
# nginx also reverse-proxies /api to the `api` service (see nginx.conf).

# Stage 1 — build.
FROM node:22-alpine AS build
WORKDIR /app
# Deps first for layer caching.
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2 — serve.
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
