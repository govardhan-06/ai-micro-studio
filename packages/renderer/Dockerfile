FROM node:22-alpine

WORKDIR /app

COPY packages/renderer/package.json packages/renderer/tsconfig.json ./
COPY packages/renderer/src ./src
RUN npm install

EXPOSE 3001
CMD ["npm", "run", "dev"]
