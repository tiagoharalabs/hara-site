FROM ghcr.io/zitadel/zitadel-login:v4.16.0
USER root
COPY hara-logo-light.svg /app/public/zitadel-logo-light.svg
COPY hara-logo-dark.svg /app/public/zitadel-logo-dark.svg
COPY hara-logo-light.svg /app/public/hara-logo-light.svg
COPY hara-logo-dark.svg /app/public/hara-logo-dark.svg
COPY favicon/ /app/public/favicon/
COPY favicon/favicon.ico /app/public/favicon.ico
COPY hara-static-server.mjs /app/hara-static-server.mjs
RUN set -eux; \
    find /app/apps/login/.next/server/chunks -type f -name '*locales*' -exec grep -Fl 'A senha foi redefinida. Por favor, verifique seu e-mail' {} + | grep -q .; \
    find /app/apps/login/.next/server/chunks -type f -name '*locales*' -exec grep -Fl 'Password was reset. Please check your email' {} + | grep -q .; \
    find /app/apps/login/.next/server/chunks -type f -name '*locales*' -exec grep -Fl 'Não foi possível enviar o link de redefinição de senha' {} + | grep -q .; \
    find /app/apps/login/.next/server/chunks -type f -name '*locales*' -exec grep -Fl 'Could not send Password Reset Link' {} + | grep -q .; \
    find /app/apps/login/.next/server/chunks -type f -name '*locales*' -exec sed -i 's/Zitadel/HARA Identity/g; s/ZITADEL/HARA Identity/g' {} +; \
    find /app/apps/login/.next/server/chunks -type f -name '*locales*' -exec sed -i 's#A senha foi redefinida. Por favor, verifique seu e-mail#Se o identificador informado estiver vinculado a uma conta com e-mail de recuperação, enviaremos as instruções ao e-mail cadastrado. Se você usou um alias ou nome de usuário, tente novamente com o e-mail cadastrado na conta.#g' {} +; \
    find /app/apps/login/.next/server/chunks -type f -name '*locales*' -exec sed -i 's#Não foi possível enviar o link de redefinição de senha#Não foi possível iniciar a recuperação. Use o endereço de e-mail cadastrado na sua conta ou entre em contato com o suporte.#g' {} +; \
    find /app/apps/login/.next/server/chunks -type f -name '*locales*' -exec sed -i 's#Password was reset. Please check your email#If the identifier is linked to an account with a recovery email, we will send instructions to the registered email address. If you used an alias or username, try again with the email registered on the account.#g' {} +; \
    find /app/apps/login/.next/server/chunks -type f -name '*locales*' -exec sed -i 's#Could not send Password Reset Link#We could not start account recovery. Use the email address registered on your account or contact support.#g' {} +; \
    find /app/apps/login/.next/server/chunks -type f -name '*.js' -exec sed -i 's/Zitadel Login/HARA Identity/g' {} +; \
    find /app/apps/login/.next/server/chunks -type f -name '*.js' -exec sed -i 's#/zitadel-logo-light.svg#/hara-logo-light.svg#g; s#/zitadel-logo-dark.svg#/hara-logo-dark.svg#g' {} +; \
    find /app/apps/login/.next/server/chunks -type f -name '*.js' -exec sed -i 's#https://zitadel.com/docs/guides/manage/user/reg-create-user#https://www.haralabs.com.br/support#g' {} +
USER nextjs
LABEL org.hara.component="identity-login" \
      org.hara.upstream="zitadel-login:v4.16.0" \
      org.hara.variant="hara.8"
