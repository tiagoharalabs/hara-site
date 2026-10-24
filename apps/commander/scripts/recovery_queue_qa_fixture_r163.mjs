// Use the actual credential resolver digest representation; never infer it from
// a SHA-256 hex file checksum. These are synthetic DEV enrollments only.
import {sha256} from '../src/oidc.js';
export const enrollmentCredentialHash=sha256;
export async function repairSyntheticCredentialSql(devices,tenant){
 if(tenant!=='HARA-R163-QUEUE-DEV-20261024'||!Array.isArray(devices)||devices.length!==50||
  new Set(devices.map(d=>d.id)).size!==devices.length||devices.some(d=>
   Object.keys(d).sort().join(',')!=='id,token'||!/^HARA-DEVICE-[0-9a-f-]{36}$/.test(d.id)||
   !/^[A-Za-z0-9_-]{32,128}$/.test(d.token)))throw Error('HOLD_SYNTHETIC_FIXTURE_SCOPE');
 return (await Promise.all(devices.map(async d=>`UPDATE commander_devices SET credential_hash='${await sha256(d.token)}'
  WHERE device_id='${d.id}' AND tenant_id='${tenant}' AND device_name='synthetic-queue';`))).join('\n');
}
