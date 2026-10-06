FROM node:22-alpine
WORKDIR /app
COPY server.mjs /app/server.mjs
COPY dcr-policy.mjs /app/dcr-policy.mjs
USER node
EXPOSE 8082
ENTRYPOINT ["node", "/app/server.mjs"]
