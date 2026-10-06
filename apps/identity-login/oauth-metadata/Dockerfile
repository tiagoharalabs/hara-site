FROM node:22-alpine
WORKDIR /app
COPY server.mjs /app/server.mjs
COPY cimd-policy.mjs /app/cimd-policy.mjs
COPY cimd-fetch.mjs /app/cimd-fetch.mjs
USER node
EXPOSE 8081
ENTRYPOINT ["node", "/app/server.mjs"]
