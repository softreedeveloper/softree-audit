# syntax=docker/dockerfile:1
FROM node:22-alpine

ENV NODE_ENV=development
WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm install

COPY apps/web/ ./

EXPOSE 4321

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
