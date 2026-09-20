# OpenAI Apps domain challenge runbook

This repository serves `./public` as the public H.A.R.A. Labs static asset tree.

The OpenAI plugin submission portal may issue an exact domain-verification token for:

`/.well-known/openai-apps-challenge`

Do **not** create a placeholder challenge file. Wait for the portal to issue the exact token.

## Safe workflow

1. Save the exact portal token into a temporary local file outside Git, for example:
   `/tmp_hara/openai-apps-challenge.token`
2. Run:
   `python3 scripts/openai_apps_challenge.py set --token-file /tmp_hara/openai-apps-challenge.token`
3. Verify locally without printing the token:
   `python3 scripts/openai_apps_challenge.py verify --token-file /tmp_hara/openai-apps-challenge.token`
4. Review the Git diff. The challenge file is intentionally public and must contain only the exact portal value.
5. Publish through the normal branch → PR → merge → Cloudflare deploy flow.
6. Confirm the public response bytes/hash match the token file.
7. Complete **Verify domain** in the OpenAI portal.
8. After the verification lifecycle no longer requires the file, remove it with:
   `python3 scripts/openai_apps_challenge.py clear`

## Safety rules

- Never invent or guess the challenge value.
- Never reuse a Cloudflare tunnel token, OAuth secret or reviewer password as the challenge.
- Do not print the token in logs or GitHub comments; record only length/SHA where useful.
- Do not bypass the normal PR/deploy workflow.
- Challenge publication is domain proof only; it does not grant H.A.R.A. runtime authority.
