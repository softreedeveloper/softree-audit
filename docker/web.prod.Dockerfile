# syntax=docker/dockerfile:1
#
# Imagen de producción del frontend.
#
# El servidor de desarrollo de Astro no se despliega: aquí se compila el sitio
# estático y lo sirve nginx, que además hace de proxy de `/api` hacia la API.
# Frontend y API quedan bajo el mismo origen, que es lo que exige el modelo de
# sesión (ADR-008): el refresh token viaja en una cookie `SameSite=Strict`.

FROM node:22-alpine AS build

WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm ci || npm install

COPY apps/web/ ./

# La ruta de la API se resuelve en tiempo de compilación: Astro genera un sitio
# estático y no hay servidor que lea variables de entorno después.
ARG PUBLIC_API_BASE_URL=/api/v1
ENV PUBLIC_API_BASE_URL=$PUBLIC_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY docker/web-nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1
