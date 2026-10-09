#!/usr/bin/env python3
"""Reconcile a *pre-enabled* ZITADEL DCR backend with a closed public edge.

Scoped: only change the Identity Docker Compose flags for guarded DCR
gateway + RFC 8414 advertisement and recreate those two services. It does
not open, use, modify, or print credentials and does not call security PUT.
Only for owner-attested backend enabled=true, allowUnauthenticated=true.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

COMPOSE = Path("/srv/hara/identity/compose/compose.yml")
SECRETS_ENV = Path("/srv/hara/identity/secrets/identity.env")
ISSUER = "https://auth.haralabs.com.br"
RFC8414 = ISSUER + "/.well-known/oauth-authorization-server"
REGISTER = ISSUER + "/oauth/v2/register"
GATEWAY = "hara-identity-zitadel-dcr-gateway-1"
META = "hara-identity-zitadel-oauth-metadata-1"
CHANGES = (
    ("HARA_DCR_GATEWAY_MODE: closed", "HARA_DCR_GATEWAY_MODE: guarded"),
    ('HARA_DCR_REGISTRATION_ADVERTISED: "false"', 'HARA_DCR_REGISTRATION_ADVERTISED: "true"'),
)
REQUIRED = (
    "hara-identity-dcr-gateway:v0.2.0",
    "hara-identity-oauth-metadata:v1.1.0",
    'HARA_DCR_TRUST_CF_CONNECTING_IP: "true"',
    'HARA_DCR_TRUST_FORWARDED_FOR: "false"',
    'HARA_DCR_REGISTRATION_LIMIT_PER_CLIENT: "10"',
    'HARA_DCR_REGISTRATION_GLOBAL_LIMIT: "200"',
    "traefik.http.routers.zitadel-dcr-gateway.priority=800",
)
PROBE = {
    "client_name": "HARA invalid public DCR guard readback",
    "application_type": "web",
    "redirect_uris": ["http://example.invalid/callback"],
    "response_types": ["code"],
    "grant_types": ["authorization_code", "refresh_token"],
    "token_endpoint_auth_method": "none",
}


def check(ok: bool, label: str):
    if not ok:
        raise RuntimeError(label)


def transition(source: str) -> str:
    for item in REQUIRED:
        check(source.count(item) == 1, "GUARDED_SECURITY_MARKER_INVALID")
    value = source
    for old, new in CHANGES:
        check(source.count(old) == 1 and source.count(new) == 0, "CLOSED_SOURCE_STATE_MISMATCH")
        value = value.replace(old, new, 1)
    check(value != source, "NO_EFFECTIVE_CHANGE")
    return value


def already_guarded(source: str) -> bool:
    return (all(source.count(old) == 0 and source.count(new) == 1
                for old, new in CHANGES)
            and all(source.count(marker) == 1 for marker in REQUIRED))


def get(url: str, *, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if data is not None else "GET",
        headers={"accept": "application/json",
                 "content-type": "application/json",
                 "user-agent": "HARA-MCP-DCR-Edge-Reconciler/1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12, context=ssl.create_default_context()) as r:
            body = r.read(65536)
            return r.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read(8192)
        try:
            body = json.loads(raw) if raw else {}
        except ValueError:
            body = {}
        return exc.code, body


def public_readback(expected: str):
    # The query disables intermediary caching without any API credentials.
    request_id = str(time.time_ns())
    status, metadata = get(RFC8414 + "?proof=" + request_id)
    check(status == 200 and metadata.get("issuer") == ISSUER, "RFC8414_METADATA_INVALID")
    registration = metadata.get("registration_endpoint")
    check((registration == REGISTER) if expected == "guarded" else (registration is None),
          "RFC8414_DCR_ADVERTISEMENT_MISMATCH")
    status, reply = get(REGISTER, payload=PROBE)
    if expected == "guarded":
        check(status == 400 and reply.get("error") == "invalid_client_metadata",
              "PUBLIC_DCR_INVALID_REGISTRATION_NOT_DENIED")
    else:
        check(status == 404, "PUBLIC_DCR_CLOSED_GATE_MISMATCH")
    return status


def container_mode():
    script = (
        "fetch('http://127.0.0.1:8082/healthz')"
        ".then(async r=>{let x=await r.json();"
        "if(!r.ok||!x.ok)process.exit(3);"
        "console.log(JSON.stringify({mode:x.mode,cf:x.trust_cf_connecting_ip,"
        "xff:x.trust_forwarded_for,per_client:x.registration_limit_per_client,"
        "global:x.registration_global_limit}))})"
        ".catch(()=>process.exit(3))"
    )
    result = subprocess.run(["docker", "exec", GATEWAY, "node", "-e", script],
                            check=True, capture_output=True, text=True, timeout=15)
    return json.loads(result.stdout.strip())


def docker_compose(*extra):
    cmd = ["docker", "compose", "--env-file", str(SECRETS_ENV),
           "-f", str(COMPOSE), *extra]
    # Do not print compose environment, tokens, secrets, or subprocess stderr.
    run = subprocess.run(cmd, capture_output=True, timeout=100)
    check(run.returncode == 0, "SCOPED_DOCKER_COMPOSE_FAILED")


def ready(expected: str):
    last = "PUBLIC_READBACK_PENDING"
    for _ in range(22):
        try:
            state = container_mode()
            check(state.get("mode") == expected, "GATEWAY_MODE_MISMATCH")
            check(state.get("cf") is True and state.get("xff") is False,
                  "IP_SOURCE_TRUST_POLICY_MISMATCH")
            check(state.get("per_client") == 10 and state.get("global") == 200,
                  "DCR_RATE_LIMIT_POLICY_MISMATCH")
            public_readback(expected)
            return
        except (RuntimeError, ValueError, urllib.error.URLError,
                subprocess.SubprocessError, json.JSONDecodeError) as exc:
            last = type(exc).__name__
            time.sleep(1)
    raise RuntimeError("EDGE_READBACK_TIMEOUT_" + last)


def atomic_write(data: bytes, source_stat):
    fd, pathname = tempfile.mkstemp(prefix=".compose.dcr.", dir=str(COMPOSE.parent))
    try:
        os.fchmod(fd, source_stat.st_mode & 0o777)
        os.fchown(fd, source_stat.st_uid, source_stat.st_gid)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pathname, COMPOSE)
    finally:
        if os.path.exists(pathname):
            os.unlink(pathname)


def test_transition():
    text = "\n".join((*REQUIRED, CHANGES[0][0], CHANGES[1][0]))
    out = transition(text)
    check(all(b in out for _, b in CHANGES), "TRANSITION_SELFTEST_FAILED")
    check(all(a not in out for a, _ in CHANGES), "PREIMAGE_STILL_PRESENT")
    check(already_guarded(out), "GUARDED_RECOGNITION_SELFTEST_FAILED")
    check(not already_guarded(text), "CLOSED_RECOGNITION_SELFTEST_FAILED")
    try:
        transition(out)
    except RuntimeError:
        pass
    else:
        raise RuntimeError("FAIL_OPEN_SELFTEST")
    print("HARA_DCR_ALREADY_OPEN_EDGE_SOURCE_SELFTEST=PASS")


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--execute", action="store_true")
    args.add_argument("--self-test", action="store_true")
    args.add_argument("--backend-already-enabled", action="store_true",
                      help="Operator attests ZITADEL enabled=true and allowUnauthenticated=true")
    options = args.parse_args()
    if options.self_test:
        test_transition()
        return 0

    check(options.backend_already_enabled, "BACKEND_STATE_ATTESTATION_REQUIRED")
    check(os.geteuid() == 0, "ROOT_REQUIRED")
    check(COMPOSE.is_file() and SECRETS_ENV.is_file(), "CANONICAL_STORAGE_LAYOUT_MISSING")
    check(COMPOSE.resolve() == Path("/srv/hara/identity/compose/compose.yml"),
          "COMPOSE_PATH_NOT_CANONICAL")

    with open("/run/lock/hara-identity-dcr-reconcile.lock", "a+b") as mutex:
        fcntl.flock(mutex, fcntl.LOCK_EX | fcntl.LOCK_NB)
        original = COMPOSE.read_bytes()
        stat = COMPOSE.stat()
        source = original.decode("utf-8")
        if already_guarded(source):
            docker_compose("config", "--quiet")
            ready("guarded")
            print("HARA_DCR_EDGE_ALREADY_GUARDED=PASS")
            print("HARA_DCR_EDGE_BACKEND_POLICY_MUTATIONS=ZERO")
            print("HARA_DCR_EDGE_EXECUTE=NO_CHANGE")
            return 0
        candidate = transition(source).encode("utf-8")
        check(hashlib.sha256(original).digest() != hashlib.sha256(candidate).digest(),
              "NO_COMPOSE_CHANGE")

        docker_compose("config", "--quiet")
        state = container_mode()
        check(state.get("mode") == "closed", "GATEWAY_NOT_CLOSED")
        ready("closed")
        print("HARA_DCR_EDGE_PREFLIGHT=CLOSED_PASS")
        print("HARA_DCR_EDGE_BACKEND_ALREADY_ENABLED=USER_ATTESTED_TRUE_TRUE")
        print("HARA_DCR_EDGE_BACKEND_POLICY_MUTATIONS=ZERO")
        print("HARA_DCR_EDGE_CANDIDATE_FLAGS=GUARDED_AND_ADVERTISED")
        print("HARA_DCR_EDGE_SECRET_OUTPUT=FALSE")
        if not options.execute:
            print("HARA_DCR_EDGE_EXECUTE=FALSE")
            return 0

        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup = COMPOSE.with_name(COMPOSE.name + ".pre-dcr-edge-reconcile-" + stamp)
        check(not backup.exists(), "BACKUP_ALREADY_EXISTS")
        shutil.copy2(COMPOSE, backup)
        os.chmod(backup, 0o600)
        backup_sha = hashlib.sha256(backup.read_bytes()).hexdigest()
        check(backup_sha == hashlib.sha256(original).hexdigest(), "BACKUP_HASH_MISMATCH")

        try:
            atomic_write(candidate, stat)
            docker_compose("config", "--quiet")
            docker_compose("up", "-d", "--no-deps",
                           "zitadel-dcr-gateway", "zitadel-oauth-metadata")
            ready("guarded")
        except BaseException as exc:
            print("HARA_DCR_EDGE_EXECUTION=ROLLBACK_TRIGGERED")
            atomic_write(original, stat)
            try:
                docker_compose("up", "-d", "--no-deps",
                               "zitadel-dcr-gateway", "zitadel-oauth-metadata")
                ready("closed")
                print("HARA_DCR_EDGE_ROLLBACK=CLOSED_PASS")
            except BaseException:
                print("HARA_DCR_EDGE_ROLLBACK=REQUIRES_OPERATOR")
                raise RuntimeError("ROLLBACK_NOT_CONFIRMED") from None
            raise RuntimeError("GUARDED_READBACK_FAILED_ROLLED_BACK") from None

        print("HARA_DCR_EDGE_EXECUTE=TRUE")
        print("HARA_DCR_EDGE_BACKUP=" + str(backup))
        print("HARA_DCR_EDGE_BACKUP_SHA256=" + backup_sha)
        print("HARA_DCR_EDGE_BACKEND_UNCHANGED=TRUE")
        print("HARA_DCR_EDGE_GATEWAY_MODE=guarded")
        print("HARA_DCR_EDGE_RFC8414_DCR_ADVERTISED=true")
        print("HARA_DCR_EDGE_INVALID_PUBLIC_REGISTRATION=DENIED")
        print("HARA_DCR_EDGE_RECONCILIATION=PASS")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.SubprocessError,
            UnicodeError, urllib.error.URLError, ValueError) as exc:
        # Deliberately avoid exception details; they may contain local paths
        # and restricted provider diagnostics. No credential information printed.
        print("HARA_DCR_EDGE_RESULT=FAIL_" + type(exc).__name__)
        raise SystemExit(2)
