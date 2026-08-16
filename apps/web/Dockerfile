FROM node:22-alpine

WORKDIR /app

COPY apps/web/package.json apps/web/tsconfig.json apps/web/next-env.d.ts apps/web/next.config.mjs ./
COPY apps/web/app ./app
RUN npm install

EXPOSE 3000
CMD ["npm", "run", "dev"]
