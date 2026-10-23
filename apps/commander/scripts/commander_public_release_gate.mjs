#!/usr/bin/env node
/** Offline public release integrity/downgrade gate. Never signs or deploys. */
import {constants, createHash, createPublicKey, verify} from 'node:crypto';

const FLOORS = Object.freeze({linux: '0.3.54', windows: '0.3.55'});
const PATHS = Object.freeze({
  linux: ['agent/linux.py', 'install/linux.sh'],
  windows: ['agent/windows.ps1', 'install/windows.ps1'],
});
const FILES = Object.freeze(['agent/linux.py', 'agent/windows.ps1', 'install/linux.sh', 'install/windows.ps1']);
const KID = 'commander-release-v2';
export const COMMERCIAL_RELEASE_POLICY = Object.freeze({
  trustedKeyId: KID,
  trustedKeySha256: '4e68608fa891f1b7a1e89c75936a089daeab0ba862a764f9bb31eca849cdfb9b',
  approvedManifestSha256: null, // owner admission remains HOLD; a bundle cannot admit itself
});
const digest = raw => createHash('sha256').update(raw).digest('hex');
function need(ok, reason) {
  if (!ok) throw new Error('COMMANDER_PUBLIC_RELEASE_HOLD_' + reason);
}
function object(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function exactKeys(value, keys) {
  return object(value) && Object.keys(value).sort().join('\0') === [...keys].sort().join('\0');
}
function document(raw, limit, label) {
  need(Buffer.isBuffer(raw) && raw.length > 0 && raw.length <= limit, label + '_BYTES');
  let value;
  try { value = JSON.parse(raw.toString('utf8')); }
  catch { throw new Error('COMMANDER_PUBLIC_RELEASE_HOLD_' + label + '_JSON'); }
  need(object(value), label + '_OBJECT');
  // Native release artifacts use this wire format. Re-rendering also rejects
  // duplicate keys, invalid UTF-8 and JSON values silently normalized by parse.
  need(raw.equals(Buffer.from(JSON.stringify(value, null, 2) + '\n')), label + '_CANONICAL_JSON');
  return value;
}
function version(raw) {
  need(typeof raw === 'string' && /^(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})$/.test(raw),
       'SEMVER');
  return raw.split('.').map(Number);
}
function compare(left, right) {
  const a = version(left), b = version(right);
  for (let i = 0; i < 3; ++i) if (a[i] !== b[i]) return Math.sign(a[i] - b[i]);
  return 0;
}
function base64url(raw, label) {
  need(typeof raw === 'string' && /^[A-Za-z0-9_-]+$/.test(raw) && raw.length <= 2048,
       label + '_BASE64URL');
  const decoded = Buffer.from(raw, 'base64url');
  need(decoded.toString('base64url') === raw, label + '_BASE64URL_CANONICAL');
  return decoded;
}

/**
 * policy.trustedKeySha256 must come from independently admitted configuration,
 * and installedVersion from trusted device observation. null explicitly means
 * a proven fresh installation; caller-provided values do not prove admission.
 */
export function validatePublicRelease(input, policy) {
  need(object(input) && object(policy) && Object.hasOwn(FLOORS, input.platform), 'PLATFORM_POLICY');
  const {platform} = input;
  const historical = policy.purpose === 'historical-integrity-audit';
  const expectedKid = policy.trustedKeyId ?? KID;
  need(expectedKid === KID || (historical && expectedKid === 'commander-release-v1'), 'RELEASE_KEY_POLICY');
  need(typeof policy.trustedKeySha256 === 'string' &&
       /^[0-9a-f]{64}$/.test(policy.trustedKeySha256), 'TRUSTED_KEY_PIN_REQUIRED');
  const publicKey = document(input.publicKey, 8192, 'PUBLIC_KEY');
  need(digest(input.publicKey) === policy.trustedKeySha256, 'PUBLIC_KEY_PIN');
  need(publicKey.kty === 'RSA' && publicKey.alg === 'RS256' && publicKey.kid === expectedKid,
       'PUBLIC_KEY_IDENTITY');
  need(exactKeys(publicKey, ['alg', 'e', 'kid', 'kty', 'n', 'use']) && publicKey.use === 'sig' &&
       !['d', 'p', 'q', 'dp', 'dq', 'qi', 'oth'].some(k => Object.hasOwn(publicKey, k)),
       'PRIVATE_KEY_FIELDS');
  const modulus = base64url(publicKey.n, 'MODULUS');
  need((expectedKid === KID ? modulus.length === 384 : modulus.length >= 256 && modulus.length <= 1024) &&
       publicKey.e === 'AQAB', 'RSA_PARAMETERS');
  const signature = document(input.signature, 8192, 'SIGNATURE');
  need(exactKeys(signature, ['schema', 'alg', 'kid', 'manifest_sha256', 'signature']) &&
       signature.schema === 'hara.commander-release-signature.v1' &&
       signature.alg === 'RS256' && signature.kid === expectedKid, 'SIGNATURE_IDENTITY');
  const manifest = document(input.manifest, 65536, 'MANIFEST');
  need(signature.manifest_sha256 === digest(input.manifest), 'MANIFEST_HASH');
  const signed = base64url(signature.signature, 'SIGNATURE');
  need(signed.length === modulus.length, 'SIGNATURE_SIZE');
  let valid = false;
  try {
    valid = verify('RSA-SHA256', input.manifest,
      {key: createPublicKey({key: publicKey, format: 'jwk'}),
       padding: constants.RSA_PKCS1_PADDING}, signed);
  } catch { valid = false; }
  need(valid, 'SIGNATURE_VERIFY');
  // Device-bound releases cannot be relabeled as a generic public channel.
  need(exactKeys(manifest, ['schema', 'product', 'channel', 'agent_version', 'files']) &&
       manifest.schema === 'hara.commander-agent-release.v1' &&
       manifest.product === 'H.A.R.A. Commander' && manifest.channel === 'stable',
       'PUBLIC_CHANNEL_CONTRACT');
  // A common-version commercial manifest must qualify BOTH platforms.
  const minimum = policy.minimumVersion ?? FLOORS[platform];
  need(compare(minimum, FLOORS[platform]) >= 0, 'POLICY_FLOOR_WEAKENED');
  if (!historical) {
    for (const floor of Object.values(FLOORS)) {
      need(compare(manifest.agent_version, floor) >= 0, 'VERSION_BELOW_FLOOR');
    }
    need(compare(manifest.agent_version, minimum) >= 0, 'VERSION_BELOW_FLOOR');
  }
  need(input.installedVersion === null || typeof input.installedVersion === 'string',
       'INSTALLED_VERSION_REQUIRED');
  if (input.installedVersion !== null) {
    need(compare(manifest.agent_version, input.installedVersion) >= 0, 'DOWNGRADE');
  }
  need(exactKeys(input.assets, FILES) && Array.isArray(manifest.files) &&
       manifest.files.length === FILES.length &&
       manifest.files.every((file, i) => file.path === FILES[i]), 'COMMERCIAL_FILESET');
  const seen = new Set();
  for (const file of manifest.files) {
    need(exactKeys(file, ['path', 'bytes', 'sha256']) &&
         FILES.includes(file.path) && !seen.has(file.path), 'FILE_PATH');
    seen.add(file.path);
    const raw = input.assets[file.path];
    need(Buffer.isBuffer(raw) && raw.length > 0 && raw.length <= 2 * 1024 * 1024,
         'ASSET_BYTES');
    need(Number.isSafeInteger(file.bytes) && file.bytes === raw.length &&
         typeof file.sha256 === 'string' && /^[0-9a-f]{64}$/.test(file.sha256) &&
         file.sha256 === digest(raw), 'ASSET_INTEGRITY');
  }
  const sums = manifest.files.map(file => `${file.sha256}  ${file.path}\n`).join('');
  need(Buffer.isBuffer(input.sha256sums) && input.sha256sums.equals(Buffer.from(sums)),
       'CHECKSUM_INDEX');
  for (const currentPlatform of Object.keys(PATHS)) {
    const [agentPath, installerPath] = PATHS[currentPlatform];
    const agent = input.assets[agentPath].toString('utf8');
    const installer = input.assets[installerPath].toString('utf8');
    const pattern = currentPlatform === 'linux'
      ? /^AGENT_VERSION\s*=\s*"([^"\r\n]+)"\s*$/gm
      : /^\$AgentVersion\s*=\s*"([^"\r\n]+)"\s*$/gm;
    const declarations = [...agent.matchAll(pattern)];
    need(declarations.length === 1 && declarations[0][1] === manifest.agent_version,
         'AGENT_VERSION_LITERAL');
    const installerPattern = currentPlatform === 'linux'
      ? /["']agent_version["']\s*:\s*["']([0-9]+\.[0-9]+\.[0-9]+)["']/g
      : /\bagent_version\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"/gi;
    const metadataPattern = currentPlatform === 'linux'
      ? /if version!="([0-9.]+)"/g : /\$manifest\.agent_version -cne "([0-9.]+)"/g;
    const literals = [...installer.matchAll(installerPattern), ...installer.matchAll(metadataPattern)];
    need(literals.length > 0 && literals.every(m => m[1] === manifest.agent_version),
         'INSTALLER_AGENT_VERSION_LITERAL');
    const names = currentPlatform === 'linux'
      ? ['RELEASE_SIGNING_KID', 'RELEASE_SIGNING_N', 'RELEASE_SIGNING_E']
      : ['\\$ReleaseSigningKid', '\\$ReleaseSigningN', '\\$ReleaseSigningE'];
    for (const [i, name] of names.entries()) {
      const matches = [...installer.matchAll(new RegExp('^' + name + '\\s*=\\s*"([^"\\r\\n]+)"\\s*$', 'gm'))];
      need(matches.length === 1 && matches[0][1] === [expectedKid, publicKey.n, publicKey.e][i],
           'INSTALLER_TRUST_ANCHOR');
    }
  }
  if (!historical) {
    need(typeof policy.approvedManifestSha256 === 'string' &&
         /^[0-9a-f]{64}$/.test(policy.approvedManifestSha256) &&
         policy.approvedManifestSha256 === digest(input.manifest), 'COMMERCIAL_ADMISSION_REQUIRED');
  }
  return {
    state: historical ? 'PASS_HISTORICAL_SIGNED_BYTES_NOT_RELEASE_APPROVAL'
      : 'PASS_PUBLIC_RELEASE_SOURCE_INTEGRITY_ONLY',
    platform, version: manifest.agent_version, manifestSha256: digest(input.manifest),
    trustedKeySha256: policy.trustedKeySha256, signatureKid: expectedKid,
    artifactCount: FILES.length, deploymentPerformed: false,
  };
}
