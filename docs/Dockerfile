FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
COPY scripts/docs ./scripts/docs

RUN npm ci

COPY docs ./docs

RUN npm run docs:build

FROM nginx:1.27-alpine AS runner

COPY docs/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/docs/.vitepress/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
