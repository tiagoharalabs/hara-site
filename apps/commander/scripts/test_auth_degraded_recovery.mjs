import assert from 'node:assert/strict';
import {
  isD1WriteLimitError,
  openAuthRecoveryPayload,
  resolveDegradedPortalSession,
  sealAuthRecoveryPayload,
} from '../src/auth.js';

const env={AUTH_CLIENT_SECRET:'test-recovery-secret-abcdefghijklmnopqrstuvwxyz'};

assert.equal(isD1WriteLimitError(new Error("D1_ERROR: Your account has exceeded D1's free tier daily row write limit. [code: 7500]")),true);
assert.equal(isD1WriteLimitError(new Error('some other database error')),false);

const tx=await sealAuthRecoveryPayload(env,'OIDC_TX',{
  state:'state-1',verifier:'verifier-1',nonce:'nonce-1',return_to:'/#devices',
  exp:Math.floor(Date.now()/1000)+600,mode:'D1_WRITE_LIMIT',
});
assert.ok(tx.startsWith('v1.'));
assert.ok(!tx.includes('verifier-1'));
const opened=await openAuthRecoveryPayload(env,'OIDC_TX',tx);
assert.equal(opened.state,'state-1');
assert.equal(opened.verifier,'verifier-1');
assert.equal(await openAuthRecoveryPayload(env,'PORTAL_SESSION',tx),null);

const sessionToken=await sealAuthRecoveryPayload(env,'PORTAL_SESSION',{
  subject_id:'HARA-SUBJECT-TEST',tenant_id:'HARA-TENANT-TEST',email:'test@example.invalid',
  display_name:'Test User',role:'OWNER',tenant_name:'Test Workspace',
  exp:Math.floor(Date.now()/1000)+1800,degraded:true,workspace_available:false,
  billing_available:true,degraded_reason:'D1_WRITE_LIMIT',
});
const req=new Request('https://commander.haralabs.com.br/api/portal/session',{
  headers:{cookie:'hara_commander_session='+encodeURIComponent(sessionToken)},
});
const session=await resolveDegradedPortalSession(req,env);
assert.equal(session.subject_id,'HARA-SUBJECT-TEST');
assert.equal(session.tenant_id,'HARA-TENANT-TEST');
assert.equal(session.role,'OWNER');
assert.equal(session.degraded,true);
assert.equal(session.workspace_available,false);
assert.equal(session.billing_available,true);
assert.equal(session.degraded_reason,'D1_WRITE_LIMIT');

const expired=await sealAuthRecoveryPayload(env,'PORTAL_SESSION',{
  subject_id:'S',tenant_id:'T',exp:Math.floor(Date.now()/1000)-1,
});
const expiredReq=new Request('https://commander.haralabs.com.br/api/portal/session',{
  headers:{cookie:'hara_commander_session='+encodeURIComponent(expired)},
});
assert.equal(await resolveDegradedPortalSession(expiredReq,env),null);

console.log('COMMANDER_AUTH_RECOVERY_D1_LIMIT_DETECTION=PASS');
console.log('COMMANDER_AUTH_RECOVERY_AES_GCM=PASS');
console.log('COMMANDER_AUTH_RECOVERY_PURPOSE_BINDING=PASS');
console.log('COMMANDER_AUTH_RECOVERY_DEGRADED_SESSION=PASS');
console.log('COMMANDER_AUTH_RECOVERY_EXPIRY=PASS');
