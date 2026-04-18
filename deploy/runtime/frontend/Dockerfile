FROM node:22-bookworm-slim AS build

ARG VITE_CCDASH_API_BASE_URL=/api
ENV VITE_CCDASH_API_BASE_URL=${VITE_CCDASH_API_BASE_URL}

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build:frontend:static

FROM nginx:1.27-alpine AS runtime

ENV CCDASH_FRONTEND_PORT=3000 \
    CCDASH_API_UPSTREAM=http://api:8000

COPY deploy/runtime/frontend/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
