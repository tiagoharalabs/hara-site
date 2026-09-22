#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys

POSTGRES_CONTAINER = "hara-identity-postgres-1"
EXPECTED_INSTANCE_NAME = "HARA Identity"
EXPECTED_DEFAULT_LANGUAGE = "pt"
EXPECTED_ALLOWED_LANGUAGES = {"pt", "en"}
EXPECTED_ROLES = {
    "391782241183268867": {"IAM_OWNER"},
    "391782241183334403": {"IAM_LOGIN_CLIENT"},
    "391835884367904771": {"IAM_OWNER"},
}
EXPECTED_PAT_COUNTS = {
    "login-client": 1,
    "hara-identity-admin": 1,
}
EXPECTED_TEMPLATE_TYPES = {
    "VerifyEmail",
    "VerifyPhone",
    "PasswordReset",
    "PasswordChange",
    "InitCode",
    "DomainClaimed",
}

def run(cmd: list[str]) -> str:
    done = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or "COMMAND_FAILED")
    return done.stdout.strip()

def sql(query: str) -> list[str]:
    out = run([
        "docker", "exec", POSTGRES_CONTAINER,
        "psql", "-U", "postgres", "-d", "zitadel",
        "-P", "pager=off", "-F", "|", "-Atqc", query,
    ])
    return [line for line in out.splitlines() if line]

def need(condition: bool, code: str) -> None:
    if not condition:
        raise AssertionError(code)

def parse_pg_array(raw: str) -> set[str]:
    raw = raw.strip()
    if raw.startswith("{") and raw.endswith("}"):
        raw = raw[1:-1]
    if not raw:
        return set()
    return {item.strip().strip('"') for item in raw.split(",") if item.strip()}

def main() -> None:
    instance_rows = sql(
        "SELECT name,default_language FROM projections.instances "
        "WHERE id='391782241182679043';"
    )
    need(len(instance_rows) == 1, "INSTANCE_ROW")
    instance_name, default_language = instance_rows[0].split("|", 1)
    need(instance_name == EXPECTED_INSTANCE_NAME, "INSTANCE_NAME")
    need(default_language == EXPECTED_DEFAULT_LANGUAGE, "DEFAULT_LANGUAGE")

    restriction_rows = sql(
        "SELECT allowed_languages,disallow_public_org_registration "
        "FROM projections.restrictions2 "
        "WHERE instance_id='391782241182679043';"
    )
    need(len(restriction_rows) == 1, "RESTRICTIONS_ROW")
    allowed_raw, public_disabled_raw = restriction_rows[0].split("|", 1)
    need(parse_pg_array(allowed_raw) == EXPECTED_ALLOWED_LANGUAGES, "ALLOWED_LANGUAGES")
    need(public_disabled_raw.lower() in {"t", "true"}, "PUBLIC_ORG_REGISTRATION")

    role_rows = sql(
        "SELECT user_id,array_to_string(roles,',') "
        "FROM projections.instance_members4 ORDER BY user_id;"
    )
    roles = {}
    for row in role_rows:
        user_id, raw_roles = row.split("|", 1)
        roles[user_id] = {r for r in raw_roles.split(",") if r}
    for user_id, expected in EXPECTED_ROLES.items():
        need(roles.get(user_id) == expected, f"ROLE:{user_id}")

    pat_rows = sql(
        "SELECT u.username,count(*) "
        "FROM projections.personal_access_tokens3 p "
        "JOIN projections.users14 u "
        "ON u.id=p.user_id AND u.instance_id=p.instance_id "
        "WHERE p.owner_removed=false "
        "GROUP BY u.username ORDER BY u.username;"
    )
    pat_counts = {}
    for row in pat_rows:
        username, count = row.split("|", 1)
        pat_counts[username] = int(count)
    for username, expected_count in EXPECTED_PAT_COUNTS.items():
        need(pat_counts.get(username) == expected_count, f"PAT_COUNT:{username}")

    template_rows = sql(
        "SELECT type,language,title,subject "
        "FROM projections.message_texts2 "
        "WHERE owner_removed=false AND language IN ('pt','en') "
        "ORDER BY type,language;"
    )
    seen = set()
    for row in template_rows:
        msg_type, language, title, subject = row.split("|", 3)
        if msg_type in EXPECTED_TEMPLATE_TYPES:
            seen.add((msg_type, language))
            visible = (title + " " + subject).lower()
            need("zitadel" not in visible, f"VENDOR_TEXT:{msg_type}:{language}")
    expected_pairs = {
        (msg_type, language)
        for msg_type in EXPECTED_TEMPLATE_TYPES
        for language in ("pt", "en")
    }
    need(seen == expected_pairs, "MAIL_TEMPLATE_COVERAGE")

    smtp_rows = sql(
        "SELECT s.host,s.tls,s.sender_address,s.sender_name,s.reply_to_address "
        "FROM projections.smtp_configs6_smtp s "
        "JOIN projections.smtp_configs6 c "
        "ON c.id=s.id AND c.instance_id=s.instance_id "
        "WHERE c.state=1 ORDER BY c.change_date DESC LIMIT 1;"
    )
    need(len(smtp_rows) == 1, "SMTP_ROW")
    host, tls_raw, sender_address, sender_name, reply_to = smtp_rows[0].split("|", 4)
    need(tls_raw.lower() in {"t", "true"}, "SMTP_TLS")
    need(sender_address == "identity@haralabs.com.br", "SMTP_SENDER_ADDRESS")
    need(sender_name == "HARA Identity", "SMTP_SENDER_NAME")
    need(reply_to == "contato@haralabs.com.br", "SMTP_REPLY_TO")
    need(host in {"smtp.zoho.com:587", "smtp.zoho.com:465"}, "SMTP_HOST")

    for container in (
        "hara-identity-zitadel-api-1",
        "hara-identity-zitadel-login-1",
        "hara-identity-zitadel-assets-1",
    ):
        health = run(["docker", "inspect", "-f", "{{.State.Health.Status}}", container])
        need(health == "healthy", f"CONTAINER_HEALTH:{container}")

    print("IDENTITY_INSTANCE_POLICY=PASS")
    print("IDENTITY_ADMIN_ROLES=PASS")
    print("IDENTITY_PAT_HYGIENE=PASS")
    print("IDENTITY_MAIL_TEMPLATE_COVERAGE=PASS")
    print("IDENTITY_ACTIVE_VENDOR_TEXT_RESIDUE=FALSE")
    print("IDENTITY_SMTP_BRANDING=PASS")
    print("IDENTITY_RUNTIME_HEALTH=PASS")
    if host == "smtp.zoho.com:587":
        print("IDENTITY_SMTP_TLS_ALIGNMENT=PENDING_587_STARTTLS_FALLBACK")
    else:
        print("IDENTITY_SMTP_TLS_ALIGNMENT=PASS_465_IMPLICIT_TLS")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"IDENTITY_BACKEND_VALIDATION=FAIL:{exc}", file=sys.stderr)
        raise
