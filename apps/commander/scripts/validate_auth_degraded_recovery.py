#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
AUTH=(ROOT/'apps/commander/src/auth.js').read_text()
WORKER=(ROOT/'apps/commander/src/worker.js').read_text()
APP=(ROOT/'apps/commander/public/app.js').read_text()

def need(ok,code):
    if not ok: raise SystemExit(f'COMMANDER_AUTH_DEGRADED_{code}=FAIL')
    print(f'COMMANDER_AUTH_DEGRADED_{code}=PASS')

need('DEGRADED_SESSION_SECONDS = 30 * 60' in AUTH,'SHORT_SESSION')
need('AES-GCM' in AUTH and 'sealAuthRecoveryPayload' in AUTH and 'openAuthRecoveryPayload' in AUTH,'SEALED_COOKIE')
need('isD1WriteLimitError' in AUTH and 'daily row write limit' in AUTH,'D1_LIMIT_CLASSIFIER')
need('txCookie=await sealAuthRecoveryPayload(env,"OIDC_TX"' in AUTH,'STATELESS_TX_FALLBACK')
need('sessionCookie=await sealAuthRecoveryPayload(env,"PORTAL_SESSION"' in AUTH,'STATELESS_SESSION_FALLBACK')
need('workspace_available:false' in AUTH and 'billing_available:true' in AUTH,'RECOVERY_SCOPE')
need('resolveDegradedPortalSession' in WORKER,'WORKER_DEGRADED_RESOLUTION')
need('WORKSPACE_BACKEND_WRITE_LIMIT' in WORKER,'WORKSPACE_BLOCK')
for path in ['/api/portal/session','/api/portal/billing','/api/portal/billing/checkout','/api/portal/billing/portal']:
    need(f'"{path}"' in WORKER,'ALLOW_'+path.split('/')[-1].upper().replace('-','_'))
need('sessionDegraded' in APP and 'Workspace temporariamente bloqueado' in APP,'UI_DEGRADED_STATE')
need('Plano e cobrança continuam disponíveis' in APP,'UI_BILLING_RECOVERY')
need('requested !== "plans"' in APP,'UI_FORCE_PLANS')
print('COMMANDER_AUTH_DEGRADED_RECOVERY=PASS')
