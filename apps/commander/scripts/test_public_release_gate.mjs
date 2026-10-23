import test from 'node:test';
import {execFileSync} from 'node:child_process';
import {COMMERCIAL_RELEASE_POLICY} from './commander_public_release_gate.mjs';
import assert from 'node:assert/strict';
import {createHash, generateKeyPairSync, sign} from 'node:crypto';
import {validatePublicRelease} from './commander_public_release_gate.mjs';

// Ephemeral test-only keys stay in this process. No production release,
// signer command, private-key file, deployment, installer or network is used.
const KEY = generateKeyPairSync('rsa', {modulusLength: 3072});
const OTHER_KEY = generateKeyPairSync('rsa', {modulusLength: 3072});
const KID = 'commander-release-v2';
const STATE = 'PASS_PUBLIC_RELEASE_SOURCE_INTEGRITY_ONLY';
const PATHS = {
  linux: ['agent/linux.py', 'install/linux.sh'],
  windows: ['agent/windows.ps1', 'install/windows.ps1'],
};
const FLOOR = {linux: '0.3.54', windows: '0.3.55'};
const sha = value => createHash('sha256').update(value).digest('hex');

function sorted(value) {
  if (Array.isArray(value)) return value.map(sorted);
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort()
      .map(key => [key, sorted(value[key])]));
  }
  return value;
}
const json = value => Buffer.from(JSON.stringify(sorted(value), null, 2) + '\n');

function seal(fixture, raw = json(fixture.document), key = KEY) {
  fixture.input.manifest = raw;
  fixture.envelope = {
    schema: 'hara.commander-release-signature.v1',
    alg: 'RS256',
    kid: KID,
    manifest_sha256: sha(raw),
    signature: sign('RSA-SHA256', raw, key.privateKey).toString('base64url'),
  };
  fixture.input.signature = json(fixture.envelope);
  fixture.policy.approvedManifestSha256 = sha(raw);
  fixture.input.sha256sums = Buffer.from(fixture.document.files.map(f => `${f.sha256}  ${f.path}\n`).join(''));
  return fixture;
}

function fixture(platform = 'linux', options = {}) {
  const version = options.version ?? '0.3.55';
  const sourceVersion = options.sourceVersion ?? version;
  const key = options.key ?? KEY;
  const jwk = {...key.publicKey.export({format: 'jwk'}), alg: 'RS256', kid: KID, use: 'sig'};
  const publicKey = json(jwk);
  const assets = {};
  for (const currentPlatform of Object.keys(PATHS)) {
    const [agentPath, installerPath] = PATHS[currentPlatform];
    const v = currentPlatform === platform ? sourceVersion : version;
    assets[agentPath] = Buffer.from(currentPlatform === 'linux'
      ? '#!/usr/bin/env python3\nAGENT_VERSION = "' + v + '"\n'
      : '$AgentVersion = "' + v + '"\n');
    assets[installerPath] = Buffer.from(currentPlatform === 'linux'
      ? `#!/bin/sh\nRELEASE_SIGNING_KID="${KID}"\nRELEASE_SIGNING_N="${jwk.n}"\nRELEASE_SIGNING_E="${jwk.e}"\n# {"agent_version":"${version}"}\n`
      : `$ReleaseSigningKid = "${KID}"\n$ReleaseSigningN = "${jwk.n}"\n$ReleaseSigningE = "${jwk.e}"\n# agent_version = "${version}"\n`);
  }
  // Files have the same order as the commercial builder, not platform groups.
  const orderedAssets = Object.fromEntries(['agent/linux.py', 'agent/windows.ps1', 'install/linux.sh', 'install/windows.ps1'].map(p => [p, assets[p]]));
  const document = {
    schema: 'hara.commander-agent-release.v1',
    product: 'H.A.R.A. Commander',
    channel: 'stable',
    agent_version: version,
    files: Object.entries(orderedAssets).map(([path, bytes]) =>
      ({path, bytes: bytes.length, sha256: sha(bytes)})),
  };
  const result = {
    document,
    input: {
      platform, manifest: null, signature: null, publicKey, assets,
      installedVersion: options.installedVersion ?? null,
    },
    policy: {trustedKeySha256: sha(publicKey)},
  };
  if (options.minimumVersion !== undefined) {
    result.policy.minimumVersion = options.minimumVersion;
  }
  return seal(result, json(document), key);
}

function accepted(f) {
  const result = validatePublicRelease(f.input, f.policy);
  assert.equal(result.state, STATE);
  assert.equal(result.deploymentPerformed, false);
  return result;
}
const denied = f => assert.throws(
  () => validatePublicRelease(f.input, f.policy), Error);

test('Linux baseline release passes source integrity only', () => {
  accepted(fixture('linux'));
});

test('Windows baseline release passes source integrity only', () => {
  accepted(fixture('windows'));
});

test('both platform invocations validate the same common-version four-file release', () => {
  const linux = fixture('linux');
  const windows = fixture('windows');
  accepted(linux);
  accepted(windows);
  assert.equal(linux.document.agent_version, windows.document.agent_version);
  assert.equal(accepted(linux).artifactCount, 4);
});

test('tampered agent and installer bytes are denied independently', () => {
  for (const path of Object.keys(fixture().input.assets)) {
    const f = fixture();
    f.input.assets[path] = Buffer.concat([f.input.assets[path], Buffer.from('# tamper')]);
    denied(f);
  }
});

test('signed but false file hashes and lengths are denied', () => {
  for (const change of [{sha256: '0'.repeat(64)}, {bytes: 1}]) {
    const f = fixture();
    Object.assign(f.document.files[0], change);
    denied(seal(f));
  }
});

test('manifest bytes cannot change under an existing signature', () => {
  const f = fixture();
  f.input.manifest = Buffer.concat([f.input.manifest, Buffer.from(' ')]);
  denied(f);
});

test('signature envelope must bind exact manifest hash', () => {
  const f = fixture();
  f.envelope.manifest_sha256 = '0'.repeat(64);
  f.input.signature = json(f.envelope);
  denied(f);
});

test('signature and public-key algorithms must both be RS256', () => {
  const badSignature = fixture();
  badSignature.envelope.alg = 'HS256';
  badSignature.input.signature = json(badSignature.envelope);
  denied(badSignature);
  const badKey = fixture();
  const key = JSON.parse(badKey.input.publicKey);
  key.alg = 'RS512';
  badKey.input.publicKey = json(key);
  badKey.policy.trustedKeySha256 = sha(badKey.input.publicKey);
  denied(badKey);
});

test('corrupted signature bytes are denied', () => {
  const f = fixture();
  const bytes = Buffer.from(f.envelope.signature, 'base64url');
  bytes[0] ^= 1;
  f.envelope.signature = bytes.toString('base64url');
  f.input.signature = json(f.envelope);
  denied(f);
});

test('wrong verification key fails even when its raw hash is trusted', () => {
  const f = fixture();
  f.input.publicKey = fixture('linux', {key: OTHER_KEY}).input.publicKey;
  f.policy.trustedKeySha256 = sha(f.input.publicKey);
  denied(f);
});

test('rotated key cannot replace the independently trusted raw JWK pin', () => {
  const f = fixture('linux', {key: OTHER_KEY});
  f.policy.trustedKeySha256 = fixture().policy.trustedKeySha256;
  denied(f);
});

test('signature and key IDs must match the enrolled release ID', () => {
  const f = fixture();
  f.envelope.kid = 'untrusted-release-id';
  f.input.signature = json(f.envelope);
  denied(f);
});

test('device-bound manifest top-level fields are denied even when signed', () => {
  for (const name of ['device_id', 'tenant_id', 'enrollment_token']) {
    const f = fixture();
    f.document[name] = 'test-only-unbound';
    denied(seal(f));
  }
});

test('traversal and noncanonical asset paths are denied', () => {
  for (const path of ['../agent/linux.py', 'agent/../agent/linux.py',
                     '/agent/linux.py', 'agent\\linux.py']) {
    const f = fixture();
    const oldPath = f.document.files[0].path;
    f.document.files[0].path = path;
    f.input.assets[path] = f.input.assets[oldPath];
    delete f.input.assets[oldPath];
    denied(seal(f));
  }
});

test('extra caller-provided assets are denied', () => {
  const f = fixture();
  f.input.assets['extra.txt'] = Buffer.from('test-only');
  denied(f);
});

test('selected agent source must declare the signed version literally', () => {
  denied(fixture('linux', {sourceVersion: '0.3.53'}));
  denied(fixture('windows', {sourceVersion: '0.3.54'}));
});

test('base floors reject old signed releases on either platform', () => {
  denied(fixture('linux', {version: '0.3.14'}));
  denied(fixture('windows', {version: '0.3.14'}));
});

test('a supplied minimum cannot lower the platform base floor', () => {
  denied(fixture('linux', {version: '0.3.14', minimumVersion: '0.3.14'}));
  denied(fixture('windows', {version: '0.3.54', minimumVersion: '0.3.14'}));
});

test('a stricter policy minimum is enforced', () => {
  denied(fixture('linux', {minimumVersion: '0.3.56'}));
});

test('installed .56 cannot downgrade to .55', () => {
  denied(fixture('linux', {version: '0.3.55', installedVersion: '0.3.56'}));
});

test('equal installed and release versions remain valid', () => {
  accepted(fixture('linux', {installedVersion: '0.3.54'}));
  accepted(fixture('windows', {installedVersion: '0.3.55'}));
});

test('numeric version comparison permits .100 after .99', () => {
  accepted(fixture('linux', {
    version: '0.3.100', installedVersion: '0.3.99', minimumVersion: '0.3.99',
  }));
});

test('malformed or zero-padded signed versions are denied', () => {
  for (const version of ['0.3', '0.3.54.1', 'v0.3.54', '0.3.54 ',
                         '00.3.54', '0.03.54', '0.3.054', '1e0.3.54']) {
    denied(fixture('linux', {version}));
  }
});

test('malformed installed versions and policy minimums are denied', () => {
  for (const version of ['latest', '0.3', '0.03.54']) {
    denied(fixture('linux', {installedVersion: version}));
    denied(fixture('linux', {minimumVersion: version}));
  }
});

test('a missing or empty signature cannot pass', () => {
  for (const value of [undefined, null, Buffer.alloc(0)]) {
    const f = fixture();
    f.input.signature = value;
    denied(f);
  }
});

test('duplicate manifest JSON keys are denied despite a valid raw signature', () => {
  const f = fixture();
  const raw = Buffer.from(f.input.manifest.toString('utf8').replace(
    '{\n', '{\n  "agent_version": "0.3.54",\n'));
  denied(seal(f, raw));
});

test('duplicate signature-envelope JSON keys are denied', () => {
  const f = fixture();
  f.input.signature = Buffer.from(f.input.signature.toString('utf8').replace(
    '{\n', '{\n  "alg": "RS256",\n'));
  denied(f);
});

test('duplicate public JWK keys are denied even under the exact raw pin', () => {
  const f = fixture();
  f.input.publicKey = Buffer.from(f.input.publicKey.toString('utf8').replace(
    '{\n', '{\n  "kid": "commander-release-v2",\n'));
  f.policy.trustedKeySha256 = sha(f.input.publicKey);
  denied(f);
});

test('manifest schema, product and channel cannot change under a valid signature', () => {
  for (const change of [
    {schema: 'hara.device-release.v1'},
    {product: 'Different product'},
    {channel: 'preview'},
  ]) {
    const f = fixture();
    Object.assign(f.document, change);
    denied(seal(f));
  }
});

test('common .54 release is held even for Linux because Windows requires .55', () => {
  assert.throws(() => validatePublicRelease(fixture('linux', {version:'0.3.54'}).input,
    fixture('linux', {version:'0.3.54'}).policy), /VERSION_BELOW_FLOOR/);
});
test('two-file platform manifests no longer qualify as a commercial bundle', () => {
  const f=fixture(); f.document.files=f.document.files.filter(r=>PATHS.linux.includes(r.path));
  f.input.assets=Object.fromEntries(Object.entries(f.input.assets).filter(([p])=>PATHS.linux.includes(p)));
  assert.throws(()=>validatePublicRelease(seal(f).input,f.policy), /COMMERCIAL_FILESET/);
});
test('installer version drift is rejected even under a fresh valid signature', () => {
  for(const p of ['install/linux.sh','install/windows.ps1']) {
    const f=fixture(); f.input.assets[p]=Buffer.from(f.input.assets[p].toString().replaceAll('0.3.55','0.3.49'));
    const r=f.document.files.find(r=>r.path===p); r.bytes=f.input.assets[p].length; r.sha256=sha(f.input.assets[p]);
    assert.throws(()=>validatePublicRelease(seal(f).input,f.policy), /INSTALLER_AGENT_VERSION_LITERAL/);
  }
});
test('signed installer trust-anchor substitution cannot pass', () => {
  const f=fixture(); const p='install/windows.ps1';
  f.input.assets[p]=Buffer.from(f.input.assets[p].toString().replace('commander-release-v2','commander-release-v1'));
  const r=f.document.files.find(r=>r.path===p); r.bytes=f.input.assets[p].length; r.sha256=sha(f.input.assets[p]);
  assert.throws(()=>validatePublicRelease(seal(f).input,f.policy), /INSTALLER_TRUST_ANCHOR/);
});
test('checksum index is bound to the same four files', () => {
  const f=fixture(); f.input.sha256sums=Buffer.from('');
  assert.throws(()=>validatePublicRelease(f.input,f.policy), /CHECKSUM_INDEX/);
});
test('stable, valid signature and current version do not admit a private RC', () => {
  const f=fixture(); delete f.policy.approvedManifestSha256;
  assert.throws(()=>validatePublicRelease(f.input,f.policy), /COMMERCIAL_ADMISSION_REQUIRED/);
});
test('wrong independently admitted manifest digest fails closed', () => {
  const f=fixture(); f.policy.approvedManifestSha256='0'.repeat(64);
  assert.throws(()=>validatePublicRelease(f.input,f.policy), /COMMERCIAL_ADMISSION_REQUIRED/);
});
test('a trusted v1 signer can be audited but cannot qualify a new commercial release', () => {
  const f=fixture();
  const jwk=JSON.parse(f.input.publicKey);jwk.kid='commander-release-v1';f.input.publicKey=json(jwk);
  for (const p of ['install/linux.sh','install/windows.ps1']) {
    f.input.assets[p]=Buffer.from(f.input.assets[p].toString().replaceAll(KID,jwk.kid));
    const r=f.document.files.find(r=>r.path===p);r.bytes=f.input.assets[p].length;r.sha256=sha(f.input.assets[p]);
  }
  seal(f);f.envelope.kid=jwk.kid;f.input.signature=json(f.envelope);
  f.policy.trustedKeySha256=sha(f.input.publicKey);f.policy.trustedKeyId=jwk.kid;
  assert.throws(()=>validatePublicRelease(f.input,f.policy), /RELEASE_KEY_POLICY/);
  f.policy.purpose='historical-integrity-audit';
  assert.equal(validatePublicRelease(f.input,f.policy).state,'PASS_HISTORICAL_SIGNED_BYTES_NOT_RELEASE_APPROVAL');
});


test('real commercial v2 four-file history is auditable but remains below release floors', t => {
  const prefix='f9f90078c5a8c4de914dd290e12607b8ecc8772c:apps/commander/release-bundles/commercial-0.3.43-v3/';
  const get=path=>execFileSync('git',['show',prefix+path],{stdio:['ignore','pipe','pipe']});
  let manifest;
  try {manifest=get('release/agent-manifest.json');}
  catch {t.skip('historical local commit unavailable');return;}
  const input={platform:'linux',installedVersion:null,manifest,
    signature:get('release/agent-manifest.sig.json'),publicKey:get('release/release-signing-public.jwk'),
    sha256sums:get('release/SHA256SUMS'),assets:Object.fromEntries(
      ['agent/linux.py','agent/windows.ps1','install/linux.sh','install/windows.ps1'].map(p=>[p,get(p)]))};
  const policy={...COMMERCIAL_RELEASE_POLICY,purpose:'historical-integrity-audit'};
  assert.equal(validatePublicRelease(input,policy).state,'PASS_HISTORICAL_SIGNED_BYTES_NOT_RELEASE_APPROVAL');
  delete policy.purpose;
  assert.throws(()=>validatePublicRelease(input,policy),/VERSION_BELOW_FLOOR/);
});
