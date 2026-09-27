const encoder = new TextEncoder();

async function digestHex(value) {
  const bytes = encoder.encode(String(value || ""));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function positiveInteger(value, code) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) throw new Error(code);
  return parsed;
}

export function fixedWindowDecision(row, limit, periodMs, nowMs) {
  const safeLimit = positiveInteger(limit, "RATE_LIMIT_LIMIT_INVALID");
  const safePeriodMs = positiveInteger(periodMs, "RATE_LIMIT_PERIOD_INVALID");
  const safeNowMs = Number(nowMs);
  if (!Number.isFinite(safeNowMs) || safeNowMs < 0) {
    throw new Error("RATE_LIMIT_CLOCK_INVALID");
  }

  const rowStart = Number(row?.window_start_ms);
  const rowCount = Number(row?.count);
  const rowValid = Number.isFinite(rowStart) && rowStart >= 0
    && Number.isInteger(rowCount) && rowCount >= 0;

  let windowStartMs = rowValid ? rowStart : safeNowMs;
  let count = rowValid ? rowCount : 0;
  if (!rowValid || safeNowMs < windowStartMs || safeNowMs >= windowStartMs + safePeriodMs) {
    windowStartMs = safeNowMs;
    count = 0;
  }

  if (count >= safeLimit) {
    return {
      success: false,
      window_start_ms: windowStartMs,
      count,
      retry_after_ms: Math.max(1, (windowStartMs + safePeriodMs) - safeNowMs),
    };
  }

  return {
    success: true,
    window_start_ms: windowStartMs,
    count: count + 1,
    retry_after_ms: 0,
  };
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

async function strictRateLimitResult(binding, key, limit, periodSeconds) {
  if (
    !binding
    || typeof binding.idFromName !== "function"
    || typeof binding.get !== "function"
  ) {
    throw new Error("STRICT_RATE_LIMIT_BINDING_MISSING");
  }

  try {
    const id = binding.idFromName(key);
    const stub = binding.get(id);
    if (!stub || typeof stub.limit !== "function") {
      throw new Error("STRICT_RATE_LIMIT_STUB_INVALID");
    }
    return await stub.limit(limit, periodSeconds);
  } catch (_error) {
    throw new Error("STRICT_RATE_LIMIT_CHECK_FAILED");
  }
}

export async function enforceLayeredRateLimit(
  fastBinding,
  strictBinding,
  key,
  limit,
  periodSeconds,
  deniedCode,
) {
  await enforceRateLimit(fastBinding, key, deniedCode);
  const result = await strictRateLimitResult(
    strictBinding,
    key,
    positiveInteger(limit, "RATE_LIMIT_LIMIT_INVALID"),
    positiveInteger(periodSeconds, "RATE_LIMIT_PERIOD_INVALID"),
  );
  if (!result?.success) throw new Error(deniedCode);
}
