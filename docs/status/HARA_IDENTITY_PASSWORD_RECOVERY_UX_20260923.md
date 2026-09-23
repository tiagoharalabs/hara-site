# H.A.R.A. Identity — password recovery UX checkpoint — 2026-09-23

State: **HARA.8 LIVE / RECOVERY UX CORRECTED / BACKEND PT UPGRADE DEFERRED**

## Tester finding

A password-recovery attempt made with an alias/username could complete the public action without producing an email. The UI then used the generic `passwordResetSent` copy, which implied that an email had definitely been sent.

## Functional cause

ZITADEL Login V2 `resetPassword` intentionally preserves anti-enumeration semantics. When `ignoreUnknownUsernames` is enabled, an unknown or non-eligible identifier may return an empty success response after a delay instead of exposing whether an account exists. The client treats that response as success and displays `password.verify.info.passwordResetSent`.

HARA therefore must not expose a literal `email not registered` response for arbitrary identifiers. The correct customer-facing contract is generic but actionable: if the identifier maps to an account with a recovery email, instructions are sent to the registered email; users who entered an alias/username are told to retry with the email registered on the account.

## Translation drift found

The prior HARA white-label applicator sent `PUT /v2/settings/hosted_login_translation` and treated HTTP 200 as terminal proof. Runtime logs nevertheless contained:

`HostedLoginTranslationNotFound-pt`

The applicator was upgraded with readback validation. The resulting proof on the current ZITADEL v4.16.0 backend is:

```text
HOSTED_LOGIN_TRANSLATION_PT=DEFERRED_UPSTREAM_V4_16_SYSTEM_LOCALE_MISSING
HOSTED_LOGIN_TRANSLATION_PT_FALSE_PASS=FALSE
HOSTED_LOGIN_TRANSLATION_EN=PASS
HOSTED_LOGIN_TRANSLATION_EN_READBACK=PASS
```

## Upstream root cause

ZITADEL v4.16.0 `internal/query/v2-default.json` does not contain a `pt` system translation. `GetHostedLoginTranslation` loads the system translation before querying the instance-level custom row, so locale `pt` returns `HostedLoginTranslationNotFound-pt` before the custom instance translation can be merged.

ZITADEL v4.17.0 includes `pt` in the backend default translation set. Upgrading API/Postgres is intentionally a separate migration gate because v4.16 -> v4.17 includes backend migrations and unrelated changes.

## Immediate safe correction

HARA login image candidate:

`hara-identity-login:v4.16.0-hara.8`

The image keeps the v4.16.0 API contract and patches only the bundled Login V2 PT/EN fallback recovery copy:

- PT success copy explains conditional delivery and recommends the registered email when an alias/username was used;
- PT failure copy recommends the registered email/support;
- equivalent EN copy is included;
- account-existence enumeration remains disabled.

Build guards fail if the expected upstream strings are absent, preventing silent patch drift.

## Candidate proof

```text
IDENTITY_V8_RECOVERY_COPY=PASS
IDENTITY_V8_CANARY_HEALTH=PASS
IDENTITY_V8_PASSWORD_PAGE_HTTP=200
IDENTITY_V8_PASSWORD_PAGE_BRANDING=PASS
```

The candidate was run on `storage` on a non-public local port against the current v4.16 API. No production route was changed during candidate validation.

## Live promotion

`hara-identity-login:v4.16.0-hara.8` is now live on `zitadel-login` and `zitadel-assets`.

Promotion changed only:

- `zitadel-login` image;
- `zitadel-assets` image.

It did not change:

- ZITADEL API image;
- Postgres;
- users;
- passwords;
- SMTP credentials;
- OIDC applications;
- Commander tenant/device data.

Post-promotion proof:

```text
zitadel-login=hara-identity-login:v4.16.0-hara.8 healthy
zitadel-assets=hara-identity-login:v4.16.0-hara.8 healthy
zitadel-api=ghcr.io/zitadel/zitadel:v4.16.0 healthy
IDENTITY_INSTANCE_POLICY=PASS
IDENTITY_ADMIN_ROLES=PASS
IDENTITY_PAT_HYGIENE=PASS
IDENTITY_MAIL_TEMPLATE_COVERAGE=PASS
IDENTITY_ACTIVE_VENDOR_TEXT_RESIDUE=FALSE
IDENTITY_SMTP_BRANDING=PASS
IDENTITY_RUNTIME_HEALTH=PASS
HARA_IDENTITY_PUBLIC_ASSETS=PASS
HARA_IDENTITY_VISIBLE_BRANDING=PASS
COMMANDER_OIDC_REDIRECT=PASS
COMMANDER_OIDC_PKCE=PASS
COMMANDER_ACCOUNT_SELECTION=PASS
HARA_IDENTITY_RECOVERY_PAGE_HTTP=PASS
HARA_IDENTITY_RECOVERY_COPY_PT=PASS
HARA_IDENTITY_RECOVERY_FALSE_SUCCESS_COPY=ABSENT
```

Normal rollback target remains `hara-identity-login:v4.16.0-hara.7`.

## Later backend improvement

Evaluate a controlled ZITADEL v4.17+ upgrade only after database backup/restore rehearsal. That later upgrade should remove the `HostedLoginTranslationNotFound-pt` backend limitation and allow the hosted PT override to read back normally.
