const encoder = new TextEncoder();

async function digestHex(value) {
  const bytes = encoder.encode(String(value || ""));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export async function rateLimitClientKey(request, scope) {
  const clientIp = String(request.headers.get("cf-connecting-ip") || "missing")
    .trim()
    .toLowerCase();
  return `${scope}:sha256:${await digestHex(clientIp)}`;
}

export async function rateLimitActorKey(scope, tenantId, subjectId) {
  return `${scope}:sha256:${await digestHex(`${tenantId}\n${subjectId}`)}`;
}

export async function rateLimitSecretKey(scope, secret) {
  return `${scope}:sha256:${await digestHex(secret)}`;
}

export async function enforceRateLimit(binding, key, deniedCode) {
  if (!binding || typeof binding.limit !== "function") {
    throw new Error("RATE_LIMIT_BINDING_MISSING");
  }
  let result;
  try {
    result = await binding.limit({ key });
  } catch (_error) {
    throw new Error("RATE_LIMIT_CHECK_FAILED");
  }
  if (!result?.success) throw new Error(deniedCode);
}
