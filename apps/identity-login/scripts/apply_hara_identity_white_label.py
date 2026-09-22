#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import urllib.error
import urllib.request

def request(base, token, method, path, body=None, headers=None, common_headers=None):
    data = None if body is None else json.dumps(body).encode()
    hdr = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if common_headers:
        hdr.update(common_headers)
    if headers:
        hdr.update(headers)
    req = urllib.request.Request(base.rstrip("/") + path, data=data, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = resp.read().decode()
            return resp.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"{method} {path} -> HTTP {exc.code}: {detail[:600]}") from exc

FOOTER_PT = "HARA Labs · Identidade e acesso seguro · haralabs.com.br"
FOOTER_EN = "HARA Labs · Secure identity and access · haralabs.com.br"
TRANSLATIONS = {
    "pt": {
        "common": {"title": "Entrar com HARA Identity"},
        "register": {"description": "Crie sua conta HARA Identity."},
        "device": {"request": {"disclaimer": "Ao clicar em Permitir, você autoriza {appName} e HARA Identity a usar as informações necessárias para autenticação e acesso. Você pode revogar este acesso a qualquer momento."}},
    },
    "en": {
        "common": {"title": "Sign in with HARA Identity"},
        "register": {"description": "Create your HARA Identity account."},
        "device": {"request": {"disclaimer": "By clicking Allow, you authorize {appName} and HARA Identity to use the information required for authentication and access. You can revoke this access at any time."}},
    },
}

MESSAGES = {
    "pt": {
        "verifyemail": ("HARA Identity — Verifique seu e-mail", "Confirme seu endereço de e-mail", "Verifique seu e-mail — HARA Labs", "Olá {{.DisplayName}},", "Para concluir a configuração da sua identidade HARA, confirme este endereço de e-mail. Código: {{.Code}}. Se você não solicitou esta ação, ignore esta mensagem.", "Verificar e-mail", FOOTER_PT),
        "verifyphone": ("HARA Identity — Verifique seu telefone", "Confirme seu número de telefone", "Verifique seu telefone — HARA Labs", "Olá {{.DisplayName}},", "Um novo número de telefone foi adicionado à sua identidade HARA. Use o código {{.Code}} para confirmar esse número. Se você não solicitou esta ação, ignore esta mensagem.", "Verificar telefone", FOOTER_PT),
        "passwordreset": ("HARA Identity — Redefinição de senha", "Redefina sua senha com segurança", "Redefina sua senha — HARA Labs", "Olá {{.DisplayName}},", "Recebemos uma solicitação para redefinir sua senha. Use o botão abaixo para continuar. Código: {{.Code}}. Se você não solicitou esta ação, ignore esta mensagem.", "Redefinir senha", FOOTER_PT),
        "password_change": ("HARA Identity — Senha alterada", "Sua senha foi alterada", "Sua senha foi alterada — HARA Labs", "Olá {{.DisplayName}},", "A senha da sua identidade HARA foi alterada. Se você não reconhece esta alteração, redefina sua senha imediatamente e entre em contato com o suporte.", "Acessar HARA Identity", FOOTER_PT),
        "init": ("HARA Identity — Ative sua conta", "Conclua a ativação da sua conta", "Ative sua conta — HARA Labs", "Olá {{.DisplayName}},", "Sua identidade HARA foi criada. Use o botão abaixo para concluir a ativação. Código: {{.Code}}.", "Ativar conta", FOOTER_PT),
        "domainclaimed": ("HARA Identity — Atualização de domínio", "Seu domínio de acesso foi atualizado", "Atualização de domínio — HARA Labs", "Olá {{.DisplayName}},", "O domínio {{.Domain}} foi associado a uma organização HARA. Para o próximo acesso, siga as instruções apresentadas pelo HARA Identity.", "Acessar HARA Identity", FOOTER_PT),
    },
    "en": {
        "verifyemail": ("HARA Identity — Verify your email", "Confirm your email address", "Verify your email — HARA Labs", "Hello {{.DisplayName}},", "To complete your HARA identity setup, confirm this email address. Code: {{.Code}}. If you did not request this action, ignore this message.", "Verify email", FOOTER_EN),
        "verifyphone": ("HARA Identity — Verify your phone", "Confirm your phone number", "Verify your phone — HARA Labs", "Hello {{.DisplayName}},", "A new phone number was added to your HARA identity. Use code {{.Code}} to confirm this number. If you did not request this action, ignore this message.", "Verify phone", FOOTER_EN),
        "passwordreset": ("HARA Identity — Password reset", "Reset your password securely", "Reset your password — HARA Labs", "Hello {{.DisplayName}},", "We received a request to reset your password. Use the button below to continue. Code: {{.Code}}. If you did not request this action, ignore this message.", "Reset password", FOOTER_EN),
        "password_change": ("HARA Identity — Password changed", "Your password was changed", "Your password was changed — HARA Labs", "Hello {{.DisplayName}},", "The password for your HARA identity was changed. If you do not recognize this change, reset your password immediately and contact support.", "Open HARA Identity", FOOTER_EN),
        "init": ("HARA Identity — Activate your account", "Complete your account activation", "Activate your account — HARA Labs", "Hello {{.DisplayName}},", "Your HARA identity was created. Use the button below to complete activation. Code: {{.Code}}.", "Activate account", FOOTER_EN),
        "domainclaimed": ("HARA Identity — Domain update", "Your access domain was updated", "Domain update — HARA Labs", "Hello {{.DisplayName}},", "The domain {{.Domain}} was associated with a HARA organization. On your next sign-in, follow the instructions shown by HARA Identity.", "Open HARA Identity", FOOTER_EN),
    },
}

def message_body(values):
    keys = ("title", "preHeader", "subject", "greeting", "text", "buttonText", "footerText")
    return dict(zip(keys, values))

def main():
    ap = argparse.ArgumentParser(description="Apply HARA Identity white-label settings.")
    ap.add_argument("--base-url", default="https://auth.haralabs.com.br")
    ap.add_argument("--pat-file", required=True)
    ap.add_argument("--host-header")
    ap.add_argument("--forwarded-proto")
    ap.add_argument("--align-smtp", action="store_true")
    ap.add_argument("--smtp-test-recipient")
    args = ap.parse_args()
    token = pathlib.Path(args.pat_file).read_text().strip()
    if not token:
        raise SystemExit("EMPTY_PAT")

    common_headers = {}
    if args.host_header:
        common_headers["Host"] = args.host_header
    if args.forwarded_proto:
        common_headers["X-Forwarded-Proto"] = args.forwarded_proto

    status, _ = request(
        args.base_url,
        token,
        "GET",
        "/admin/v1/text/default/message/verifyemail/pt",
        common_headers=common_headers,
    )
    if status != 200:
        raise SystemExit(f"IAM_OWNER_PREFLIGHT_FAILED:{status}")
    print("IAM_OWNER_PREFLIGHT=PASS")
    request(
        args.base_url, token, "POST",
        "/zitadel.instance.v2.InstanceService/UpdateInstance",
        {"instanceName": "HARA Identity"},
        {"Connect-Protocol-Version": "1"},
        common_headers=common_headers,
    )
    print("INSTANCE_NAME=PASS")

    request(
        args.base_url, token, "PUT", "/admin/v1/restrictions",
        {"disallowPublicOrgRegistration": True, "allowedLanguages": {"list": ["pt", "en"]}},
        common_headers=common_headers,
    )
    print("LANGUAGE_RESTRICTIONS=PASS")

    for locale, translations in TRANSLATIONS.items():
        request(
            args.base_url, token, "PUT", "/v2/settings/hosted_login_translation",
            {"instance": True, "locale": locale, "translations": translations},
            common_headers=common_headers,
        )
        print(f"HOSTED_LOGIN_TRANSLATION_{locale.upper()}=PASS")

    for locale, templates in MESSAGES.items():
        for template, values in templates.items():
            request(
                args.base_url, token, "PUT",
                f"/admin/v1/text/message/{template}/{locale}",
                message_body(values),
                common_headers=common_headers,
            )
            print(f"MESSAGE_{template}_{locale}=PASS")

    if args.align_smtp:
        smtp_id = "391802825635528707"
        request(
            args.base_url,
            token,
            "PUT",
            f"/admin/v1/smtp/{smtp_id}",
            {
                "id": smtp_id,
                "senderAddress": "identity@haralabs.com.br",
                "senderName": "HARA Identity",
                "tls": True,
                "host": "smtp.zoho.com:465",
                "user": "tiago@haralabs.com.br",
                "replyToAddress": "contato@haralabs.com.br",
                "description": "HARA Identity Zoho",
            },
            common_headers=common_headers,
        )
        print("SMTP_TLS_PORT_ALIGNMENT=PASS")

        if args.smtp_test_recipient:
            request(
                args.base_url,
                token,
                "POST",
                f"/admin/v1/smtp/{smtp_id}/_test",
                {"id": smtp_id, "receiverAddress": args.smtp_test_recipient},
                common_headers=common_headers,
            )
            print("SMTP_PROVIDER_TEST=PASS")

    print("HARA_IDENTITY_WHITE_LABEL=PASS")

if __name__ == "__main__":
    main()
