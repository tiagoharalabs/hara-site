#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import stat
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HARNESS = ROOT / "apps/commander/scripts/commander_e2e_harness.py"
PROVISION = ROOT / "apps/commander/scripts/provision_mcp_product_token.py"

def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"{name.upper()}_IMPORT=FAIL")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

harness = load_module("commander_e2e_harness_validation", HARNESS)
provision = load_module("commander_token_provision_validation", PROVISION)

HarnessError = harness.HarnessError
load_token = harness.load_token

with tempfile.TemporaryDirectory(prefix="hara-token-hardening-") as tmp:
    root = Path(tmp)
    secret_dir = root / "secret"
    token_path = secret_dir / "mcp-token"

    provision._secure_secret_dir(secret_dir)
    token = provision._create_token(token_path)

    assert len(token) >= 48
    assert load_token(token_path) == token

    if os.name != "nt":
        assert stat.S_IMODE(os.stat(secret_dir).st_mode) == 0o700
        assert stat.S_IMODE(os.stat(token_path).st_mode) == 0o600
    print("COMMANDER_MCP_TOKEN_STORAGE_SECURE_CREATE=PASS")

    if os.name != "nt":
        token_path.chmod(0o644)
        try:
            load_token(token_path)
        except HarnessError as exc:
            assert str(exc) == "MCP_PRODUCT_TOKEN_FILE_PERMISSIONS"
        else:
            raise SystemExit("COMMANDER_MCP_TOKEN_STORAGE_LOOSE_MODE_DENIED=FAIL")

        try:
            provision._read_existing_token(token_path)
        except RuntimeError as exc:
            assert str(exc) == "MCP_PRODUCT_TOKEN_FILE_PERMISSIONS"
        else:
            raise SystemExit("COMMANDER_MCP_TOKEN_PROVISION_LOOSE_MODE_DENIED=FAIL")
        token_path.chmod(0o600)
        print("COMMANDER_MCP_TOKEN_STORAGE_LOOSE_MODE_DENIED=PASS")

    target = root / "target-token"
    target.write_text("x" * 64, encoding="utf-8")
    if os.name != "nt":
        target.chmod(0o600)
    link = root / "token-link"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        print("COMMANDER_MCP_TOKEN_STORAGE_SYMLINK_TEST=SKIP")
    else:
        try:
            load_token(link)
        except HarnessError as exc:
            assert str(exc) == "MCP_PRODUCT_TOKEN_FILE_UNSAFE"
        else:
            raise SystemExit("COMMANDER_MCP_TOKEN_STORAGE_SYMLINK_DENIED=FAIL")

        try:
            provision._read_existing_token(link)
        except RuntimeError as exc:
            assert str(exc) == "MCP_PRODUCT_TOKEN_FILE_UNSAFE"
        else:
            raise SystemExit("COMMANDER_MCP_TOKEN_PROVISION_SYMLINK_DENIED=FAIL")
        print("COMMANDER_MCP_TOKEN_STORAGE_SYMLINK_DENIED=PASS")

harness_source = HARNESS.read_text(encoding="utf-8")
provision_source = PROVISION.read_text(encoding="utf-8")
assert "info.st_uid != os.getuid()" in harness_source
assert "info.st_uid != os.getuid()" in provision_source
assert "O_NOFOLLOW" in harness_source and "O_NOFOLLOW" in provision_source
assert 'WRANGLER_VERSION = "4.137.0"' in provision_source
assert "4.136.1" not in provision_source
assert "print(token" not in provision_source
assert "MCP_PRODUCT_TOKEN_VALUE_EXPOSED=FALSE" in provision_source

print("COMMANDER_MCP_TOKEN_STORAGE_OWNER_GUARD=PASS")
print("COMMANDER_MCP_TOKEN_STORAGE_NOFOLLOW=PASS")
print("COMMANDER_MCP_TOKEN_PROVISION_WRANGLER_PIN=PASS")
print("COMMANDER_MCP_TOKEN_VALUE_EXPOSED=FALSE")
print("COMMANDER_MCP_TOKEN_STORAGE=PASS")
