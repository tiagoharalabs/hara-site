#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import tempfile
import urllib.parse

FORBIDDEN_VISIBLE = (
    "Entrar com Zitadel",
    "Crie sua conta Zitadel",
    "ZITADEL Login",
    "Zitadel Login",
    "zitadel.com/docs",
)

RECOVERY_COPY_PT = (
    "Se o identificador informado estiver vinculado a uma conta com e-mail de recuperação, "
    "enviaremos as instruções ao e-mail cadastrado. Se você usou um alias ou nome de usuário, "
    "tente novamente com o e-mail cadastrado na conta."
)
RECOVERY_OLD_FALSE_SUCCESS_PT = "A senha foi redefinida. Por favor, verifique seu e-mail"

def curl(url, *, follow=False, cookie_jar=None):
    cmd = [
        "curl", "-sS", "--retry", "3", "--retry-delay", "1",
        "--connect-timeout", "10", "--max-time", "30",
        "-o", "-", "-w",
        "\n__HARA_STATUS__:%{http_code}\n__HARA_REDIRECT__:%{redirect_url}",
    ]
    if follow:
        cmd.append("-L")
    if cookie_jar:
        cmd += ["-c", str(cookie_jar), "-b", str(cookie_jar)]
    cmd.append(url)
    done = subprocess.run(cmd, capture_output=True, check=False)
    if done.returncode != 0:
        error = done.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"CURL_FAILED:{url}:{error}")
    marker = b"\n__HARA_STATUS__:"
    if marker not in done.stdout:
        raise RuntimeError(f"CURL_STATUS_MISSING:{url}")
    body, meta = done.stdout.rsplit(marker, 1)
    status_raw, redirect_raw = meta.split(b"\n__HARA_REDIRECT__:", 1)
    status = int(status_raw.strip().decode("ascii"))
    redirect = redirect_raw.strip().decode("utf-8", errors="replace")
    return status, redirect, body

def need(condition, code):
    if not condition:
        raise AssertionError(code)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity", default="https://auth.haralabs.com.br")
    parser.add_argument(
        "--commander",
        default="https://hara-commander-dev-v2.tiago-sartori.workers.dev",
    )
    parser.add_argument("--client-id", default="391790882505949187")
    args = parser.parse_args()

    identity = args.identity.rstrip("/")
    commander = args.commander.rstrip("/")

    status, _, raw = curl(identity + "/favicon/site.webmanifest")
    need(status == 200, "MANIFEST_HTTP")
    manifest = json.loads(raw)
    need(manifest.get("name") == "HARA Identity", "MANIFEST_NAME")
    need(manifest.get("short_name") == "HARA Identity", "MANIFEST_SHORT_NAME")
    icon_paths = {item.get("src") for item in manifest.get("icons", [])}
    need("/favicon/android-chrome-192x192.png" in icon_paths, "MANIFEST_ICON_192")
    need("/favicon/android-chrome-512x512.png" in icon_paths, "MANIFEST_ICON_512")

    for path in (
        "/favicon/favicon.ico",
        "/favicon.ico",
        "/hara-logo-light.svg",
        "/hara-logo-dark.svg",
    ):
        status, _, body = curl(identity + path)
        need(status == 200, f"ASSET_HTTP:{path}")
        need(len(body) > 300, f"ASSET_TOO_SMALL:{path}")
        if path.endswith(".svg"):
            text = body.decode("utf-8")
            need("<svg" in text and "H.A.R.A. Labs" in text, f"HARA_LOGO_INVALID:{path}")

    status, location, _ = curl(commander + "/auth/login")
    need(status == 302, "COMMANDER_AUTH_REDIRECT_HTTP")
    parsed = urllib.parse.urlparse(location)
    query = urllib.parse.parse_qs(parsed.query)
    need(parsed.scheme == "https", "OIDC_SCHEME")
    need(parsed.netloc == "auth.haralabs.com.br", "OIDC_HOST")
    need(parsed.path == "/oauth/v2/authorize", "OIDC_AUTHORIZE_PATH")
    need(query.get("client_id") == [args.client_id], "OIDC_CLIENT_ID")
    need(query.get("prompt") == ["select_account"], "OIDC_ACCOUNT_SELECTION")
    need(query.get("code_challenge_method") == ["S256"], "OIDC_PKCE")
    with tempfile.TemporaryDirectory() as temp:
        cookie_jar = pathlib.Path(temp) / "cookies.txt"
        status, _, body = curl(
            commander + "/auth/login",
            follow=True,
            cookie_jar=cookie_jar,
        )
    need(status == 200, "HARA_LOGIN_PAGE_HTTP")
    page = body.decode("utf-8", errors="replace")
    need("Entrar com HARA Identity" in page, "HARA_LOGIN_TITLE")
    need("Crie sua conta HARA Identity" in page, "HARA_REGISTER_COPY")
    for token in FORBIDDEN_VISIBLE:
        need(token not in page, f"VISIBLE_VENDOR_LEAK:{token}")

    recovery_url = identity + "/ui/v2/login/password?loginName=qa-alias-does-not-exist"
    status, _, recovery_body = curl(recovery_url)
    need(status == 200, "RECOVERY_PAGE_HTTP")
    recovery_page = recovery_body.decode("utf-8", errors="replace")
    need(RECOVERY_COPY_PT in recovery_page, "RECOVERY_COPY_PT_MISSING")
    need(RECOVERY_OLD_FALSE_SUCCESS_PT not in recovery_page, "RECOVERY_FALSE_SUCCESS_COPY_PRESENT")

    print("HARA_IDENTITY_PUBLIC_ASSETS=PASS")
    print("HARA_IDENTITY_MANIFEST=PASS")
    print("HARA_IDENTITY_VISIBLE_BRANDING=PASS")
    print("HARA_IDENTITY_VISIBLE_VENDOR_LEAK=FALSE")
    print("COMMANDER_OIDC_REDIRECT=PASS")
    print("COMMANDER_OIDC_PKCE=PASS")
    print("COMMANDER_ACCOUNT_SELECTION=PASS")
    print("HARA_IDENTITY_RECOVERY_PAGE_HTTP=PASS")
    print("HARA_IDENTITY_RECOVERY_COPY_PT=PASS")
    print("HARA_IDENTITY_RECOVERY_FALSE_SUCCESS_COPY=ABSENT")

if __name__ == "__main__":
    main()
