#!/usr/bin/env bash
set -Eeuo pipefail

HARA_COMMANDER_URL="${HARA_COMMANDER_URL:-https://commander.haralabs.com.br}"
HARA_BOOTSTRAP_TRUST_COMMIT="35d9a5e19e045ebbfdd128360dddbe6c72a569fe"
HARA_BOOTSTRAP_GITHUB_BASE="https://raw.githubusercontent.com/tiagoharalabs/hara-site/${HARA_BOOTSTRAP_TRUST_COMMIT}/apps/commander/public"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'HARA_BOOTSTRAP_REQUIRED_COMMAND_MISSING=%s\n' "$1" >&2
    exit 2
  }
}

need curl
need sha256sum
need cmp
need bash

case "$HARA_COMMANDER_URL" in
  https://*) ;;
  *) printf 'HARA_BOOTSTRAP_HTTPS_REQUIRED=TRUE\n' >&2; exit 3 ;;
esac

tmpdir="$(mktemp -d)"
chmod 700 "$tmpdir"
trap 'rm -rf "$tmpdir"' EXIT

fetch() {
  local url="$1" out="$2"
  curl -fsS --proto '=https' --tlsv1.2 --location --max-redirs 0 --max-time 30 "$url" -o "$out"
}

hara_installer="$tmpdir/hara-linux.sh"
github_installer="$tmpdir/github-linux.sh"
hara_key="$tmpdir/hara-release-key.jwk"
github_key="$tmpdir/github-release-key.jwk"

fetch "$HARA_COMMANDER_URL/install/linux.sh" "$hara_installer" || {
  printf 'HARA_BOOTSTRAP_PRIMARY_INSTALLER_FETCH_FAILED=TRUE\n' >&2
  exit 10
}
fetch "$HARA_BOOTSTRAP_GITHUB_BASE/install/linux.sh" "$github_installer" || {
  printf 'HARA_BOOTSTRAP_GITHUB_INSTALLER_FETCH_FAILED=TRUE\n' >&2
  exit 11
}
fetch "$HARA_COMMANDER_URL/release/release-signing-public.jwk" "$hara_key" || {
  printf 'HARA_BOOTSTRAP_PRIMARY_KEY_FETCH_FAILED=TRUE\n' >&2
  exit 12
}
fetch "$HARA_BOOTSTRAP_GITHUB_BASE/release/release-signing-public.jwk" "$github_key" || {
  printf 'HARA_BOOTSTRAP_GITHUB_KEY_FETCH_FAILED=TRUE\n' >&2
  exit 13
}

if ! cmp -s "$hara_installer" "$github_installer"; then
  printf 'HARA_BOOTSTRAP_INSTALLER_ORIGIN_MISMATCH=TRUE\n' >&2
  printf 'HARA_BOOTSTRAP_PRIMARY_SHA256=%s\n' "$(sha256sum "$hara_installer" | awk '{print $1}')" >&2
  printf 'HARA_BOOTSTRAP_GITHUB_SHA256=%s\n' "$(sha256sum "$github_installer" | awk '{print $1}')" >&2
  exit 20
fi

if ! cmp -s "$hara_key" "$github_key"; then
  printf 'HARA_BOOTSTRAP_RELEASE_KEY_ORIGIN_MISMATCH=TRUE\n' >&2
  exit 21
fi

installer_sha="$(sha256sum "$hara_installer" | awk '{print $1}')"
key_sha="$(sha256sum "$hara_key" | awk '{print $1}')"

printf 'HARA_BOOTSTRAP_DUAL_ORIGIN=PASS\n'
printf 'HARA_BOOTSTRAP_TRUST_COMMIT=%s\n' "$HARA_BOOTSTRAP_TRUST_COMMIT"
printf 'HARA_BOOTSTRAP_INSTALLER_SHA256=%s\n' "$installer_sha"
printf 'HARA_BOOTSTRAP_RELEASE_KEY_SHA256=%s\n' "$key_sha"

if [ "${1:-}" = "--verify-only" ]; then
  printf 'HARA_BOOTSTRAP_VERIFY_ONLY=PASS\n'
  exit 0
fi

HARA_COMMANDER_URL="$HARA_COMMANDER_URL" \
HARA_COMMANDER_APPROVAL_MODE="${HARA_COMMANDER_APPROVAL_MODE:-PERSISTENT_TRUSTED}" \
bash "$hara_installer" "$@"
