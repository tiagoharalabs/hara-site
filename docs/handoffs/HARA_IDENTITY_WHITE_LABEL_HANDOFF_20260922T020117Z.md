# HARA Identity white-label handoff — 2026-09-22

## Live state

- Public issuer: `https://auth.haralabs.com.br/`
- Commander DEV: `https://hara-commander-dev-v2.tiago-sartori.workers.dev/`
- Login image: `hara-identity-login:v4.16.0-hara.1`
- Live image digest: `sha256:2070fdfc96ec0c7ad28d65dbf33ec2d76c59c946dc300040f2b9c5003d1e1516`
- Login container health: `healthy`
- Upstream remains ZITADEL Login V2 4.16.0; API, issuer, Session API and OIDC semantics are unchanged.
- Commander login still emits PKCE S256 + `prompt=select_account`.

## Visible UX proof

Following `/auth/login` from Commander renders `Entrar com HARA Identity` / `Crie sua conta HARA Identity`.
No visible `Zitadel` / `ZITADEL` string was found in the rendered login page.
## Runtime theme

- `NEXT_PUBLIC_APPLICATION_NAME=HARA Identity`
- layout: `side-by-side`
- appearance: `material`
- spacing: `compact`
- roundness: `mid`
- Branding policy already uses HARA colors/logos and disables the vendor watermark.

## Mail transport

Current SMTP provider is already HARA-branded:
`identity@haralabs.com.br`, sender `HARA Identity`, reply-to `contato@haralabs.com.br`.

## Remaining administrative action

Message texts are still vendor defaults until an `IAM_OWNER` PAT is supplied.
Run `apps/identity-login/scripts/apply_hara_identity_white_label.py --pat-file <secure-owner-pat>`.
The script uses supported APIs only; do not edit ZITADEL projections/event store directly.
It also renames the instance to `HARA Identity` and restricts supported languages to `pt` and `en`.
