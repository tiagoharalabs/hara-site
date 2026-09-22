FROM ghcr.io/zitadel/zitadel-login:v4.16.0
USER root
COPY hara-logo-light.svg /app/public/zitadel-logo-light.svg
COPY hara-logo-dark.svg /app/public/zitadel-logo-dark.svg
RUN set -eux; \
    find /app/apps/login/.next/server/chunks -type f -name '*locales*' -exec sed -i 's/Zitadel/HARA Identity/g; s/ZITADEL/HARA Identity/g' {} +; \
    find /app/apps/login/.next/server/chunks -type f -name '*.js' -exec sed -i 's/Zitadel Login/HARA Identity/g' {} +; \
    find /app/apps/login/.next/server/chunks -type f -name '*.js' -exec sed -i 's#https://zitadel.com/docs/guides/manage/user/reg-create-user#https://www.haralabs.com.br/support#g' {} +; \
    sed -i 's/ZITADEL Login/HARA Identity/g' /app/public/favicon/site.webmanifest
USER nextjs
LABEL org.hara.component="identity-login" \
      org.hara.upstream="zitadel-login:v4.16.0" \
      org.hara.variant="hara.1"
