import {
  exchangeAuthorizationCode,
  normalizeIssuer,
  oidcDiscovery,
  oidcUserInfo,
  pkceChallenge,
  randomToken,
  sha256,
  verifyIdToken,
} from "./oidc.js";

const AUTH_SECURITY_HEADERS = Object.freeze({
  "strict-transport-security": "max-age=31536000; includeSubDomains",
  "x-content-type-options": "nosniff",
  "x-frame-options": "DENY",
  "referrer-policy": "no-referrer",
  "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  "x-robots-tag": "noindex, nofollow",
});

const SESSION_COOKIE = "hara_commander_session";
const TX_COOKIE = "hara_commander_oidc_tx";
const SESSION_SECONDS = 8 * 60 * 60;
const DEGRADED_SESSION_SECONDS = 30 * 60;
const TX_SECONDS = 10 * 60;
const RECOVERY_COOKIE_PREFIX = "v1.";
const TX_RETENTION_BATCH = 100;
const SESSION_TOUCH_SECONDS = 30 * 60;
const SESSION_RETENTION_SECONDS = 30 * 24 * 60 * 60;
const SESSION_RETENTION_BATCH = 100;

function nowIso(offsetSeconds = 0) {
  return new Date(Date.now() + offsetSeconds * 1000).toISOString();
}

function b64urlEncode(bytes) {
  let binary="";
  const view=bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  for (const byte of view) binary+=String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/g,"");
}

function b64urlDecode(value) {
  const text=String(value || "");
  const padded=text.replace(/-/g,"+").replace(/_/g,"/")+"===".slice((text.length+3)%4);
  const binary=atob(padded);
  const out=new Uint8Array(binary.length);
  for (let i=0;i<binary.length;i+=1) out[i]=binary.charCodeAt(i);
  return out;
}

function recoverySecret(env) {
  const secret=String(env.AUTH_SESSION_RECOVERY_SECRET || env.AUTH_CLIENT_SECRET || "").trim();
  if (secret.length < 16) throw new Error("AUTH_RECOVERY_SECRET_NOT_CONFIGURED");
  return secret;
}

async function recoveryKey(env,purpose) {
  const encoder=new TextEncoder();
  const material=await crypto.subtle.digest(
    "SHA-256",
    encoder.encode("HARA_COMMANDER_AUTH_RECOVERY_V1\n"+String(purpose)+"\n"+recoverySecret(env)),
  );
  return crypto.subtle.importKey("raw",material,{name:"AES-GCM"},false,["encrypt","decrypt"]);
}

export async function sealAuthRecoveryPayload(env,purpose,payload) {
  const encoder=new TextEncoder();
  const iv=crypto.getRandomValues(new Uint8Array(12));
  const key=await recoveryKey(env,purpose);
  const plaintext=encoder.encode(JSON.stringify(payload));
  const ciphertext=await crypto.subtle.encrypt({name:"AES-GCM",iv},key,plaintext);
  return RECOVERY_COOKIE_PREFIX+b64urlEncode(iv)+"."+b64urlEncode(ciphertext);
}

export async function openAuthRecoveryPayload(env,purpose,token) {
  const text=String(token || "");
  if (!text.startsWith(RECOVERY_COOKIE_PREFIX)) return null;
  const parts=text.split(".");
  if (parts.length !== 3 || parts[0] !== "v1") return null;
  try {
    const iv=b64urlDecode(parts[1]);
    const ciphertext=b64urlDecode(parts[2]);
    if (iv.length !== 12 || ciphertext.length < 17) return null;
    const key=await recoveryKey(env,purpose);
    const plaintext=await crypto.subtle.decrypt({name:"AES-GCM",iv},key,ciphertext);
    const payload=JSON.parse(new TextDecoder().decode(plaintext));
    if (!payload || typeof payload !== "object") return null;
    return payload;
  } catch (_error) {
    return null;
  }
}

export function isD1WriteLimitError(error) {
  const text=String(error?.message || error || "").toLowerCase();
  return text.includes("d1") && (
    text.includes("daily row write limit")
    || text.includes("free tier daily row write limit")
  );
}

function degradedSessionLocation() {
  return "/?workspace=degraded&reason=D1_WRITE_LIMIT#plans";
}

export function cookieValue(request, name) {
  const header = request.headers.get("cookie") || "";
  for (const part of header.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key !== name) continue;
    try {
      return decodeURIComponent(rest.join("="));
    } catch (_error) {
      return null;
    }
  }
  return null;
}

function setCookie(name, value, { maxAge, path = "/", secure = true } = {}) {
  const parts = [
    name + "=" + encodeURIComponent(value),
    "Path=" + path,
    "HttpOnly",
    "SameSite=Lax",
  ];
  if (secure) parts.push("Secure");
  if (Number.isFinite(maxAge)) parts.push("Max-Age=" + Math.max(0, Math.floor(maxAge)));
  return parts.join("; ");
}

function clearCookie(name, path = "/") {
  return setCookie(name, "", { maxAge: 0, path });
}

export function authCallbackFailureResponse(error) {
  const raw = String(error?.message || "AUTH_CALLBACK_FAILED");
  const safeCode = /^[A-Z0-9_]{1,80}$/.test(raw) ? raw : "AUTH_CALLBACK_FAILED";
  const headers = new Headers({
    ...AUTH_SECURITY_HEADERS,
    location: "/?auth_error=" + encodeURIComponent(safeCode) + "#login",
    "cache-control": "no-store",
  });
  headers.append("set-cookie", clearCookie(TX_COOKIE, "/auth"));
  return new Response(null, { status: 302, headers });
}

const SAFE_RETURN_ORIGIN = "https://commander.invalid";

export function safeReturnTo(value) {
  const fallback = "/#dashboard";
  const text = String(value || fallback);
  if (
    !text.startsWith("/")
    || text.length > 500
    || /[\\\u0000-\u001f\u007f]/.test(text)
  ) return fallback;
  try {
    const resolved = new URL(text, SAFE_RETURN_ORIGIN);
    if (resolved.origin !== SAFE_RETURN_ORIGIN || !resolved.pathname.startsWith("/")) {
      return fallback;
    }
  } catch (_error) {
    return fallback;
  }
  return text;
}

function normalizeEmail(value) {
  const email = String(value || "").trim().toLowerCase();
  if (!email || email.length > 320 || !email.includes("@")) return null;
  return email;
}

export async function productionProvisioningPlan(env, issuer, subject) {
  if (String(env.ENVIRONMENT || "") !== "PROD") return "TRIAL";
  const expected = String(env.FOUNDER_INTERNAL_IDENTITY_FINGERPRINT || "").trim();
  if (!/^[A-Za-z0-9_-]{43}$/.test(expected)) return "TRIAL";
  const fingerprint = await sha256(normalizeIssuer(issuer) + "\n" + String(subject));
  return fingerprint === expected ? "FOUNDER_INTERNAL" : "TRIAL";
}

export function authStatus(env) {
  const clientAuth = String(env.AUTH_CLIENT_AUTH || "BASIC").trim().toUpperCase();
  const clientAuthSupported = clientAuth === "BASIC" || clientAuth === "NONE";
  const credentialsReady = (
    clientAuth === "NONE"
    || (clientAuth === "BASIC" && Boolean(env.AUTH_CLIENT_SECRET))
  );
  const configured = Boolean(
    clientAuthSupported
    && env.AUTH_ISSUER
    && env.AUTH_CLIENT_ID
    && credentialsReady
  );
  return {
    configured,
    provider: env.AUTH_PROVIDER_LABEL || "HARA Identity",
    client_auth: clientAuth,
  };
}

function authConfig(env) {
  const status = authStatus(env);
  if (!status.configured) throw new Error("OIDC_NOT_CONFIGURED");
  return {
    issuer: normalizeIssuer(env.AUTH_ISSUER),
    clientId: String(env.AUTH_CLIENT_ID),
    clientSecret: String(env.AUTH_CLIENT_SECRET || ""),
    clientAuth: status.client_auth,
    provider: status.provider,
  };
}

async function cleanupExpiredOidcTransactions(env) {
  const now = nowIso();
  await env.PRODUCT_DB.prepare(
    `DELETE FROM oidc_transactions
      WHERE state_hash IN (
        SELECT state_hash
          FROM oidc_transactions
         WHERE expires_at_utc <= ?
         ORDER BY expires_at_utc ASC
         LIMIT ?
      )`
  ).bind(now, TX_RETENTION_BATCH).run().catch(() => null);
}

async function cleanupTerminalPortalSessions(env) {
  const cutoff = nowIso(-SESSION_RETENTION_SECONDS);
  await env.PRODUCT_DB.prepare(
    `DELETE FROM portal_sessions
      WHERE session_hash IN (
        SELECT session_hash
          FROM portal_sessions
         WHERE expires_at_utc <= ?
            OR (revoked_at_utc IS NOT NULL AND revoked_at_utc <= ?)
         ORDER BY COALESCE(revoked_at_utc, expires_at_utc) ASC
         LIMIT ${SESSION_RETENTION_BATCH}
      )`
  ).bind(cutoff, cutoff).run().catch(() => null);
}

export async function runAuthRetentionMaintenance(env) {
  await cleanupExpiredOidcTransactions(env);
  await cleanupTerminalPortalSessions(env);
}

export async function beginLogin(request, env) {
  const config = authConfig(env);
  const metadata = await oidcDiscovery(config.issuer);
  const url = new URL(request.url);
  const redirectUri = url.origin + "/auth/callback";
  const returnTo = safeReturnTo(url.searchParams.get("return_to"));

  // Retention hygiene runs on the Worker's scheduled maintenance path.
  // Login remains independent from non-authoritative cleanup work.

  const state = randomToken(32);
  const browserBinding = randomToken(32);
  const verifier = randomToken(64);
  const nonce = randomToken(32);
  const challenge = await pkceChallenge(verifier);
  const stateHash = await sha256(state);
  const bindingHash = await sha256(browserBinding);

  let txCookie=browserBinding;
  try {
    await env.PRODUCT_DB.prepare(
      `INSERT INTO oidc_transactions
        (state_hash, browser_binding_hash, code_verifier, nonce, return_to, created_at_utc, expires_at_utc, consumed_at_utc)
       VALUES (?, ?, ?, ?, ?, ?, ?, NULL)`
    ).bind(
      stateHash,
      bindingHash,
      verifier,
      nonce,
      returnTo,
      nowIso(),
      nowIso(TX_SECONDS),
    ).run();
  } catch (error) {
    if (!isD1WriteLimitError(error)) throw error;
    txCookie=await sealAuthRecoveryPayload(env,"OIDC_TX",{
      state,
      verifier,
      nonce,
      return_to:returnTo,
      exp:Math.floor(Date.now()/1000)+TX_SECONDS,
      mode:"D1_WRITE_LIMIT",
    });
  }

  const authorize = new URL(metadata.authorization_endpoint);
  authorize.searchParams.set("response_type", "code");
  authorize.searchParams.set("client_id", config.clientId);
  authorize.searchParams.set("redirect_uri", redirectUri);
  authorize.searchParams.set("scope", "openid profile email");
  authorize.searchParams.set("state", state);
  authorize.searchParams.set("nonce", nonce);
  authorize.searchParams.set("code_challenge", challenge);
  authorize.searchParams.set("code_challenge_method", "S256");
  if (url.searchParams.get("screen_hint") === "signup") {
    authorize.searchParams.set("prompt", "create");
  } else if (url.searchParams.get("force_login") === "1") {
    // "Usar outra conta" must select an account, not merely reauthenticate
    // whichever HARA Identity session happened to be current.
    authorize.searchParams.set("prompt", "select_account");
    authorize.searchParams.set("max_age", "0");
  } else {
    authorize.searchParams.set("prompt", "select_account");
  }

  return new Response(null, {
    status: 302,
    headers: {
      ...AUTH_SECURITY_HEADERS,
      location: authorize.toString(),
      "set-cookie": setCookie(TX_COOKIE, txCookie, { maxAge: TX_SECONDS, path: "/auth" }),
      "cache-control": "no-store",
    },
  });
}

async function ensurePrimaryIdentityBinding(env, subjectId, issuer, externalSubject) {
  await env.PRODUCT_DB.prepare(
    `INSERT OR IGNORE INTO identity_bindings
      (identity_binding_id, subject_id, provider_code, issuer, external_subject, state, created_at_utc, revoked_at_utc)
     VALUES (?, ?, 'PRIMARY_OIDC', ?, ?, 'ACTIVE', ?, NULL)`
  ).bind(
    "PRIMARY:" + subjectId,
    subjectId,
    issuer,
    externalSubject,
    nowIso(),
  ).run();
}

async function provisionProductionIdentity(env, claims, issuer, subject, email) {
  if (String(env.ENVIRONMENT || "") !== "PROD") return null;
  const fingerprint = await sha256(issuer + "\n" + subject);
  const planCode = await productionProvisioningPlan(env, issuer, subject);
  const tenantId = "HARA-TENANT-" + fingerprint.slice(0, 24).toUpperCase();
  const subjectId = "HARA-SUBJECT-" + fingerprint.slice(24, 48).toUpperCase();
  const entitlementId = "HARA-ENTITLEMENT-" + fingerprint.slice(40, 64).toUpperCase();
  const displayName = String(claims.name || claims.nickname || email).slice(0, 200);
  const createdAt = nowIso();

  await env.PRODUCT_DB.batch([
    env.PRODUCT_DB.prepare(
      `INSERT OR IGNORE INTO tenants
        (tenant_id, display_name, state, environment, created_at_utc)
       VALUES (?, ?, 'ACTIVE', 'PRODUCTION', ?)`
    ).bind(tenantId, displayName || "Commander", createdAt),
    env.PRODUCT_DB.prepare(
      `INSERT OR IGNORE INTO users
        (subject_id, tenant_id, oidc_issuer, oidc_subject, email, display_name,
         state, role, created_at_utc)
       VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', 'OWNER', ?)`
    ).bind(subjectId, tenantId, issuer, subject, email, displayName, createdAt),
    env.PRODUCT_DB.prepare(
      `INSERT OR IGNORE INTO identity_bindings
        (identity_binding_id, subject_id, provider_code, issuer, external_subject,
         state, created_at_utc, revoked_at_utc)
       VALUES (?, ?, 'PRIMARY_OIDC', ?, ?, 'ACTIVE', ?, NULL)`
    ).bind("PRIMARY:" + subjectId, subjectId, issuer, subject, createdAt),
    env.PRODUCT_DB.prepare(
      `INSERT OR IGNORE INTO entitlements
        (entitlement_id, tenant_id, subject_id, plan_code, state, valid_from_utc, valid_until_utc)
       VALUES (?, ?, ?, ?, 'ACTIVE', ?, NULL)`
    ).bind(entitlementId, tenantId, subjectId, planCode, createdAt),
  ]);

  return env.PRODUCT_DB.prepare(
    `SELECT subject_id, tenant_id, oidc_issuer, oidc_subject, email, display_name, state, role
       FROM users
      WHERE oidc_issuer = ? AND oidc_subject = ?
      LIMIT 1`
  ).bind(issuer, subject).first();
}

async function resolveOrClaimIdentity(env, claims) {
  const issuer = normalizeIssuer(claims.iss);
  const subject = String(claims.sub);

  let user = await env.PRODUCT_DB.prepare(
    `SELECT subject_id, tenant_id, oidc_issuer, oidc_subject, email, display_name, state, role
       FROM users
      WHERE oidc_issuer = ? AND oidc_subject = ?
      LIMIT 1`
  ).bind(issuer, subject).first();

  if (user) {
    if (user.state !== "ACTIVE") throw new Error("IDENTITY_INACTIVE");
    try {
      await ensurePrimaryIdentityBinding(env, user.subject_id, issuer, subject);
    } catch (error) {
      if (!isD1WriteLimitError(error)) throw error;
    }
    return user;
  }

  const email = claims.email_verified === true ? normalizeEmail(claims.email) : null;
  if (!email) throw new Error("IDENTITY_NOT_PROVISIONED");

  const invite = await env.PRODUCT_DB.prepare(
    `SELECT invite_id, normalized_email, target_subject_id, state, expires_at_utc
       FROM identity_invites
      WHERE normalized_email = ?
      LIMIT 1`
  ).bind(email).first();

  if (!invite || invite.state !== "ACTIVE") {
    const provisioned = await provisionProductionIdentity(env, claims, issuer, subject, email);
    if (!provisioned || provisioned.state !== "ACTIVE") {
      throw new Error("IDENTITY_NOT_PROVISIONED");
    }
    return provisioned;
  }
  if (invite.expires_at_utc && invite.expires_at_utc <= nowIso()) throw new Error("IDENTITY_INVITE_EXPIRED");

  const target = await env.PRODUCT_DB.prepare(
    `SELECT subject_id, tenant_id, state
       FROM users
      WHERE subject_id = ?
      LIMIT 1`
  ).bind(invite.target_subject_id).first();

  if (!target || target.state !== "ACTIVE") throw new Error("IDENTITY_INVITE_TARGET_INVALID");

  const displayName = String(claims.name || claims.nickname || email).slice(0, 200);
  const claimedAt = nowIso();

  await env.PRODUCT_DB.batch([
    env.PRODUCT_DB.prepare(
      `UPDATE identity_invites
          SET state = 'CLAIMED', claimed_at_utc = ?, claimed_issuer = ?, claimed_subject = ?
        WHERE invite_id = ? AND state = 'ACTIVE'`
    ).bind(claimedAt, issuer, subject, invite.invite_id),
    env.PRODUCT_DB.prepare(
      `UPDATE users
          SET oidc_issuer = ?, oidc_subject = ?, email = ?, display_name = ?
        WHERE subject_id = ?
          AND state = 'ACTIVE'
          AND EXISTS (
            SELECT 1
              FROM identity_invites i
             WHERE i.invite_id = ?
               AND i.state = 'CLAIMED'
               AND i.claimed_at_utc = ?
               AND i.claimed_issuer = ?
               AND i.claimed_subject = ?
          )`
    ).bind(
      issuer, subject, email, displayName, target.subject_id,
      invite.invite_id, claimedAt, issuer, subject,
    ),
    env.PRODUCT_DB.prepare(
      `INSERT OR IGNORE INTO identity_bindings
        (identity_binding_id, subject_id, provider_code, issuer, external_subject,
         state, created_at_utc, revoked_at_utc)
       SELECT ?, ?, 'PRIMARY_OIDC', ?, ?, 'ACTIVE', ?, NULL
        WHERE EXISTS (
          SELECT 1
            FROM identity_invites i
           WHERE i.invite_id = ?
             AND i.state = 'CLAIMED'
             AND i.claimed_at_utc = ?
             AND i.claimed_issuer = ?
             AND i.claimed_subject = ?
        )`
    ).bind(
      "PRIMARY:" + target.subject_id, target.subject_id, issuer, subject, claimedAt,
      invite.invite_id, claimedAt, issuer, subject,
    ),
  ]);

  user = await env.PRODUCT_DB.prepare(
    `SELECT subject_id, tenant_id, oidc_issuer, oidc_subject, email, display_name, state, role
       FROM users
      WHERE oidc_issuer = ? AND oidc_subject = ?
      LIMIT 1`
  ).bind(issuer, subject).first();

  if (!user || user.state !== "ACTIVE") throw new Error("IDENTITY_BINDING_FAILED");
  return user;
}

export async function finishLogin(request, env) {
  const config = authConfig(env);
  const url = new URL(request.url);

  if (url.searchParams.get("error")) {
    throw new Error("OIDC_PROVIDER_ERROR");
  }

  const code = String(url.searchParams.get("code") || "");
  const state = String(url.searchParams.get("state") || "");
  const browserBinding = cookieValue(request, TX_COOKIE);
  if (!code || !state || !browserBinding) throw new Error("OIDC_CALLBACK_INVALID");

  let tx;
  let recoveryTx=false;
  if (String(browserBinding).startsWith(RECOVERY_COOKIE_PREFIX)) {
    const recovered=await openAuthRecoveryPayload(env,"OIDC_TX",browserBinding);
    if (!recovered || recovered.state !== state) throw new Error("OIDC_STATE_INVALID");
    if (Number(recovered.exp || 0) <= Math.floor(Date.now()/1000)) throw new Error("OIDC_STATE_EXPIRED");
    tx={
      code_verifier:String(recovered.verifier || ""),
      nonce:String(recovered.nonce || ""),
      return_to:safeReturnTo(recovered.return_to),
    };
    if (!tx.code_verifier || !tx.nonce) throw new Error("OIDC_STATE_INVALID");
    recoveryTx=true;
  } else {
    const stateHash = await sha256(state);
    const bindingHash = await sha256(browserBinding);
    tx = await env.PRODUCT_DB.prepare(
      `SELECT state_hash, browser_binding_hash, code_verifier, nonce, return_to, expires_at_utc, consumed_at_utc
         FROM oidc_transactions
        WHERE state_hash = ?
        LIMIT 1`
    ).bind(stateHash).first();

    if (!tx || tx.browser_binding_hash !== bindingHash) throw new Error("OIDC_STATE_INVALID");
    if (tx.consumed_at_utc) throw new Error("OIDC_STATE_REPLAYED");
    if (tx.expires_at_utc <= nowIso()) throw new Error("OIDC_STATE_EXPIRED");

    try {
      const consumed = await env.PRODUCT_DB.prepare(
        `UPDATE oidc_transactions
            SET consumed_at_utc = ?
          WHERE state_hash = ? AND consumed_at_utc IS NULL`
      ).bind(nowIso(), stateHash).run();
      if (!consumed.meta?.changes) throw new Error("OIDC_STATE_REPLAYED");
    } catch (error) {
      if (!isD1WriteLimitError(error)) throw error;
      recoveryTx=true;
    }
  }

  const metadata = await oidcDiscovery(config.issuer);
  const redirectUri = url.origin + "/auth/callback";
  const tokens = await exchangeAuthorizationCode({
    metadata,
    clientId: config.clientId,
    clientSecret: config.clientSecret,
    clientAuth: config.clientAuth,
    code,
    verifier: tx.code_verifier,
    redirectUri,
  });

  const claims = await verifyIdToken({
    idToken: tokens.id_token,
    metadata,
    issuer: config.issuer,
    clientId: config.clientId,
    nonce: tx.nonce,
  });

  let identityClaims = claims;
  if (claims.email_verified !== true || !normalizeEmail(claims.email)) {
    const userInfo = await oidcUserInfo({ metadata, accessToken: tokens.access_token });
    if (String(userInfo.sub) !== String(claims.sub)) throw new Error("OIDC_USERINFO_SUBJECT_MISMATCH");
    identityClaims = { ...claims, ...userInfo, iss: claims.iss, sub: claims.sub };
  }

  const user = await resolveOrClaimIdentity(env, identityClaims);
  const sessionToken = randomToken(48);
  const sessionHash = await sha256(sessionToken);
  const createdAt = nowIso();
  const expiresAt = nowIso(SESSION_SECONDS);

  let sessionCookie=sessionToken;
  let sessionMaxAge=SESSION_SECONDS;
  let location=safeReturnTo(tx.return_to);
  try {
    await env.PRODUCT_DB.prepare(
      `INSERT INTO portal_sessions
        (session_hash, subject_id, created_at_utc, expires_at_utc, last_seen_at_utc, revoked_at_utc)
       VALUES (?, ?, ?, ?, ?, NULL)`
    ).bind(sessionHash, user.subject_id, createdAt, expiresAt, createdAt).run();
  } catch (error) {
    if (!isD1WriteLimitError(error)) throw error;
    const tenant=await env.PRODUCT_DB.prepare(
      `SELECT display_name,state FROM tenants WHERE tenant_id = ? LIMIT 1`
    ).bind(user.tenant_id).first().catch(()=>null);
    if (tenant?.state && tenant.state !== "ACTIVE") throw new Error("IDENTITY_INACTIVE");
    sessionCookie=await sealAuthRecoveryPayload(env,"PORTAL_SESSION",{
      subject_id:user.subject_id,
      tenant_id:user.tenant_id,
      email:user.email || null,
      display_name:user.display_name || user.email || "Conta HARA",
      role:user.role || "MEMBER",
      tenant_name:tenant?.display_name || "Seu workspace",
      exp:Math.floor(Date.now()/1000)+DEGRADED_SESSION_SECONDS,
      degraded:true,
      workspace_available:false,
      billing_available:true,
      degraded_reason:"D1_WRITE_LIMIT",
      recovery_tx:recoveryTx,
    });
    sessionMaxAge=DEGRADED_SESSION_SECONDS;
    location=degradedSessionLocation();
  }

  const headers = new Headers({
    ...AUTH_SECURITY_HEADERS,
    location,
    "cache-control": "no-store",
  });
  headers.append("set-cookie", setCookie(SESSION_COOKIE, sessionCookie, { maxAge: sessionMaxAge, path: "/" }));
  headers.append("set-cookie", clearCookie(TX_COOKIE, "/auth"));

  return new Response(null, { status: 302, headers });
}

export async function resolveDegradedPortalSession(request, env) {
  const token=cookieValue(request,SESSION_COOKIE);
  if (!token || !String(token).startsWith(RECOVERY_COOKIE_PREFIX)) return null;
  const recovered=await openAuthRecoveryPayload(env,"PORTAL_SESSION",token);
  if (!recovered || Number(recovered.exp || 0) <= Math.floor(Date.now()/1000)) return null;
  if (!recovered.subject_id || !recovered.tenant_id) return null;
  return {
    subject_id:String(recovered.subject_id),
    tenant_id:String(recovered.tenant_id),
    email:recovered.email || null,
    display_name:String(recovered.display_name || "Conta HARA"),
    role:String(recovered.role || "MEMBER"),
    tenant_name:String(recovered.tenant_name || "Seu workspace"),
    user_state:"ACTIVE",
    tenant_state:"ACTIVE",
    degraded:true,
    workspace_available:false,
    billing_available:true,
    degraded_reason:String(recovered.degraded_reason || "BACKEND_WRITE_UNAVAILABLE"),
  };
}

export async function resolvePortalSession(request, env) {
  const token = cookieValue(request, SESSION_COOKIE);
  if (!token) return null;
  if (String(token).startsWith(RECOVERY_COOKIE_PREFIX)) {
    return resolveDegradedPortalSession(request,env);
  }
  const hash = await sha256(token);

  const session = await env.PRODUCT_DB.prepare(
    `SELECT
       s.session_hash,
       s.subject_id,
       s.expires_at_utc,
       s.last_seen_at_utc,
       s.revoked_at_utc,
       u.tenant_id,
       u.oidc_issuer,
       u.oidc_subject,
       u.email,
       u.display_name,
       u.state AS user_state,
       u.role,
       t.display_name AS tenant_name,
       t.state AS tenant_state
     FROM portal_sessions s
     JOIN users u ON u.subject_id = s.subject_id
     JOIN tenants t ON t.tenant_id = u.tenant_id
    WHERE s.session_hash = ?
    LIMIT 1`
  ).bind(hash).first();

  if (!session) return null;
  if (session.revoked_at_utc || session.expires_at_utc <= nowIso()) return null;
  if (session.user_state !== "ACTIVE" || session.tenant_state !== "ACTIVE") return null;

  const seenAt = Date.parse(String(session.last_seen_at_utc || ""));
  const now = Date.now();
  if (!Number.isFinite(seenAt) || now - seenAt >= SESSION_TOUCH_SECONDS * 1000) {
    // Session liveness telemetry must never make an already-valid session fail.
    await env.PRODUCT_DB.prepare(
      `UPDATE portal_sessions SET last_seen_at_utc = ? WHERE session_hash = ?`
    ).bind(new Date(now).toISOString(), hash).run().catch(() => null);
  }

  return session;
}

export async function logout(request, env) {
  const token = cookieValue(request, SESSION_COOKIE);
  if (token && !String(token).startsWith(RECOVERY_COOKIE_PREFIX)) {
    const hash = await sha256(token);
    await env.PRODUCT_DB.prepare(
      `UPDATE portal_sessions SET revoked_at_utc = ? WHERE session_hash = ? AND revoked_at_utc IS NULL`
    ).bind(nowIso(), hash).run().catch((error)=>{ if (!isD1WriteLimitError(error)) throw error; });
  }

  return new Response(null, {
    status: 204,
    headers: {
      ...AUTH_SECURITY_HEADERS,
      "set-cookie": clearCookie(SESSION_COOKIE, "/"),
      "cache-control": "no-store",
    },
  });
}
