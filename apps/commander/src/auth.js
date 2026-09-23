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
const TX_SECONDS = 10 * 60;

function nowIso(offsetSeconds = 0) {
  return new Date(Date.now() + offsetSeconds * 1000).toISOString();
}

function cookieValue(request, name) {
  const header = request.headers.get("cookie") || "";
  for (const part of header.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
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

function safeReturnTo(value) {
  const text = String(value || "/#dashboard");
  if (!text.startsWith("/") || text.startsWith("//") || text.length > 500) return "/#dashboard";
  return text;
}

function normalizeEmail(value) {
  const email = String(value || "").trim().toLowerCase();
  if (!email || email.length > 320 || !email.includes("@")) return null;
  return email;
}

export function authStatus(env) {
  const clientAuth = String(env.AUTH_CLIENT_AUTH || "BASIC").trim().toUpperCase();
  const credentialsReady = clientAuth === "NONE" || Boolean(env.AUTH_CLIENT_SECRET);
  const configured = Boolean(env.AUTH_ISSUER && env.AUTH_CLIENT_ID && credentialsReady);
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
    provider: status.provider,
  };
}

export async function beginLogin(request, env) {
  const config = authConfig(env);
  const metadata = await oidcDiscovery(config.issuer);
  const url = new URL(request.url);
  const redirectUri = url.origin + "/auth/callback";
  const returnTo = safeReturnTo(url.searchParams.get("return_to"));

  const state = randomToken(32);
  const browserBinding = randomToken(32);
  const verifier = randomToken(64);
  const nonce = randomToken(32);
  const challenge = await pkceChallenge(verifier);
  const stateHash = await sha256(state);
  const bindingHash = await sha256(browserBinding);

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
    authorize.searchParams.set("prompt", "login");
  } else {
    authorize.searchParams.set("prompt", "select_account");
  }

  return new Response(null, {
    status: 302,
    headers: {
      ...AUTH_SECURITY_HEADERS,
      location: authorize.toString(),
      "set-cookie": setCookie(TX_COOKIE, browserBinding, { maxAge: TX_SECONDS, path: "/auth" }),
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
       VALUES (?, ?, ?, 'TRIAL', 'ACTIVE', ?, NULL)`
    ).bind(entitlementId, tenantId, subjectId, createdAt),
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
    await ensurePrimaryIdentityBinding(env, user.subject_id, issuer, subject);
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
      `UPDATE users
          SET oidc_issuer = ?, oidc_subject = ?, email = ?, display_name = ?
        WHERE subject_id = ? AND state = 'ACTIVE'`
    ).bind(issuer, subject, email, displayName, target.subject_id),
    env.PRODUCT_DB.prepare(
      `UPDATE identity_invites
          SET state = 'CLAIMED', claimed_at_utc = ?, claimed_issuer = ?, claimed_subject = ?
        WHERE invite_id = ? AND state = 'ACTIVE'`
    ).bind(claimedAt, issuer, subject, invite.invite_id),
    env.PRODUCT_DB.prepare(
      `INSERT OR IGNORE INTO identity_bindings
        (identity_binding_id, subject_id, provider_code, issuer, external_subject, state, created_at_utc, revoked_at_utc)
       VALUES (?, ?, 'PRIMARY_OIDC', ?, ?, 'ACTIVE', ?, NULL)`
    ).bind("PRIMARY:" + target.subject_id, target.subject_id, issuer, subject, claimedAt),
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

  const stateHash = await sha256(state);
  const bindingHash = await sha256(browserBinding);
  const tx = await env.PRODUCT_DB.prepare(
    `SELECT state_hash, browser_binding_hash, code_verifier, nonce, return_to, expires_at_utc, consumed_at_utc
       FROM oidc_transactions
      WHERE state_hash = ?
      LIMIT 1`
  ).bind(stateHash).first();

  if (!tx || tx.browser_binding_hash !== bindingHash) throw new Error("OIDC_STATE_INVALID");
  if (tx.consumed_at_utc) throw new Error("OIDC_STATE_REPLAYED");
  if (tx.expires_at_utc <= nowIso()) throw new Error("OIDC_STATE_EXPIRED");

  const consumed = await env.PRODUCT_DB.prepare(
    `UPDATE oidc_transactions
        SET consumed_at_utc = ?
      WHERE state_hash = ? AND consumed_at_utc IS NULL`
  ).bind(nowIso(), stateHash).run();

  if (!consumed.meta?.changes) throw new Error("OIDC_STATE_REPLAYED");

  const metadata = await oidcDiscovery(config.issuer);
  const redirectUri = url.origin + "/auth/callback";
  const tokens = await exchangeAuthorizationCode({
    metadata,
    clientId: config.clientId,
    clientSecret: config.clientSecret,
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

  await env.PRODUCT_DB.prepare(
    `INSERT INTO portal_sessions
      (session_hash, subject_id, created_at_utc, expires_at_utc, last_seen_at_utc, revoked_at_utc)
     VALUES (?, ?, ?, ?, ?, NULL)`
  ).bind(sessionHash, user.subject_id, createdAt, expiresAt, createdAt).run();

  const headers = new Headers({
    ...AUTH_SECURITY_HEADERS,
    location: safeReturnTo(tx.return_to),
    "cache-control": "no-store",
  });
  headers.append("set-cookie", setCookie(SESSION_COOKIE, sessionToken, { maxAge: SESSION_SECONDS, path: "/" }));
  headers.append("set-cookie", clearCookie(TX_COOKIE, "/auth"));

  return new Response(null, { status: 302, headers });
}

export async function resolvePortalSession(request, env) {
  const token = cookieValue(request, SESSION_COOKIE);
  if (!token) return null;
  const hash = await sha256(token);

  const session = await env.PRODUCT_DB.prepare(
    `SELECT
       s.session_hash,
       s.subject_id,
       s.expires_at_utc,
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

  await env.PRODUCT_DB.prepare(
    `UPDATE portal_sessions SET last_seen_at_utc = ? WHERE session_hash = ?`
  ).bind(nowIso(), hash).run();

  return session;
}

export async function logout(request, env) {
  const token = cookieValue(request, SESSION_COOKIE);
  if (token) {
    const hash = await sha256(token);
    await env.PRODUCT_DB.prepare(
      `UPDATE portal_sessions SET revoked_at_utc = ? WHERE session_hash = ? AND revoked_at_utc IS NULL`
    ).bind(nowIso(), hash).run();
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
