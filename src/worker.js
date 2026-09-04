function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store"
    }
  });
}

function cleanText(value, maxLength = 1000) {
  return String(value || "")
    .replace(/[<>{}[\]\\`]/g, "")
    .replace(/https?:\/\/\S+/gi, "[link removido]")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLength);
}

function cleanArray(value, maxLength = 700) {
  if (!Array.isArray(value)) return [];

  return value
    .map((item) => cleanText(item, 80))
    .filter(Boolean)
    .slice(0, 40)
    .join(", ")
    .slice(0, maxLength);
}

function isLikelyEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || "").trim());
}

function publicText(value, maxLength = 240) {
  const internalPathPattern = new RegExp('/(?:srv' + '/hara|tmp_' + 'hara)(?:/[^\\s]*)?', 'gi');
  const privateIpPattern = new RegExp(
    '(?:10[.](?:[0-9]{1,3}[.]){2}[0-9]{1,3}|' +
      '192[.]' + '168[.](?:[0-9]{1,3}[.])[0-9]{1,3}|' +
      '172[.](?:1[6-9]|2[0-9]|3[01])[.](?:[0-9]{1,3}[.])[0-9]{1,3})',
    'g'
  );

  return cleanText(value, maxLength)
    .replace(/\bnucleo-a\b/gi, "Nó observado")
    .replace(/\bsentinela-[a-d]\b/gi, "Nó observado")
    .replace(/\bninja[ -]blue\b/gi, "Infraestrutura observada")
    .replace(/\bhara-fleet-[a-z0-9-]+-node\b/gi, "Alvo observado")
    .replace(/\bObserver\b/gi, "Coleta de telemetria")
    .replace(/\b(?:túnel SSH|SSH tunnel|loopback)\b/gi, "transporte interno")
    .replace(internalPathPattern, "[caminho interno]")
    .replace(privateIpPattern, "[endereço interno]");
}

function publicSignal(signal = {}, fallbackLabel = "Sinal") {
  const projected = {
    label: publicText(signal.label || fallbackLabel, 80),
    state: publicText(signal.state || "unknown", 40),
    display: publicText(signal.display ?? signal.value ?? "—", 80),
    detail: publicText(signal.detail || "", 240)
  };

  if (typeof signal.value === "number" && Number.isFinite(signal.value)) {
    projected.value = signal.value;
  }
  if (typeof signal.total === "number" && Number.isFinite(signal.total)) {
    projected.total = signal.total;
  }
  if (typeof signal.up === "number" && Number.isFinite(signal.up)) {
    projected.up = signal.up;
  }

  return projected;
}

function publicObservabilityProjection(payload = {}) {
  const signals = payload.signals || {};
  const projectedSignals = {};
  const allowedSignals = {
    disk: "Uso de armazenamento observado",
    failed_units: "Unidades com falha",
    journal_errors: "Erros recentes",
    observer: "Coleta de telemetria",
    snapshot: "Frescor do snapshot",
    targets: "Alvos essenciais"
  };

  for (const [key, fallbackLabel] of Object.entries(allowedSignals)) {
    if (signals[key] && typeof signals[key] === "object") {
      projectedSignals[key] = publicSignal(signals[key], fallbackLabel);
    }
  }

  const components = Array.isArray(payload.components)
    ? payload.components.slice(0, 12).map((component) => ({
        name: publicText(component?.name || "Componente", 80),
        state: publicText(component?.state || "unknown", 40),
        summary: publicText(component?.summary || "", 240)
      }))
    : [];

  const governance = payload.governance || {};
  const freshness = payload.freshness || {};

  return {
    schema: "hara.public-observability.v1",
    generated_at_utc: cleanText(payload.generated_at_utc || "", 80),
    overall_state: publicText(payload.overall_state || "unknown", 40),
    overall_message: publicText(payload.overall_message || "Snapshot público sanitizado.", 240),
    freshness: {
      maximum_expected_seconds: Number.isFinite(Number(freshness.maximum_expected_seconds))
        ? Math.max(30, Math.min(3600, Number(freshness.maximum_expected_seconds)))
        : 180
    },
    governance: {
      state: publicText(governance.state || "unknown", 40),
      summary: publicText(governance.summary || "Governança sem detalhe público.", 240),
      direct_main_push: Number(governance.direct_main_push || 0),
      force_push: Number(governance.force_push || 0),
      merge: Number(governance.merge || 0)
    },
    components,
    signals: projectedSignals
  };
}

async function verifyTurnstile(token, secret, remoteIp) {
  if (!secret) {
    return {
      success: false,
      "error-codes": ["turnstile-secret-not-configured"]
    };
  }

  try {
    const response = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST",
      headers: {
        "content-type": "application/json"
      },
      body: JSON.stringify({
        secret,
        response: token,
        remoteip: remoteIp
      })
    });

    if (!response.ok) {
      return {
        success: false,
        "error-codes": [`siteverify-http-${response.status}`]
      };
    }

    return await response.json();
  } catch (_error) {
    return {
      success: false,
      "error-codes": ["siteverify-request-failed"]
    };
  }
}

function missingRequired(payload) {
  const required = [
    ["nome", "Nome"],
    ["email", "E-mail"],
    ["empresa", "Empresa"],
    ["cargo", "Cargo / função"],
    ["tipoEmpresa", "Perfil da empresa"],
    ["colaboradores", "Quantidade de colaboradores"],
    ["decisao", "Origem das decisões de TI"],
    ["sede", "País da sede / matriz"],
    ["objetivo", "Objetivo principal"],
    ["urgencia", "Urgência"],
    ["sponsor", "Patrocinador interno"],
    ["documentacao", "Documentação dos processos"],
    ["donoDados", "Dono dos dados"],
    ["maturidade", "Maturidade percebida"],
    ["erp", "ERP principal"],
    ["crm", "CRM principal"]
  ];

  return required
    .filter(([key]) => !payload[key])
    .map(([, label]) => label);
}

async function saveDiagnosticToR2(env, payload, request) {
  if (!env.DIAGNOSTICS_BUCKET) {
    throw new Error("DIAGNOSTICS_BUCKET não configurado.");
  }

  const now = new Date();
  const iso = now.toISOString();
  const day = iso.slice(0, 10);
  const randomPart = crypto.randomUUID();
  const key =
    `diagnosticos/raw/${day}/` +
    `${iso.replace(/[:.]/g, "-")}_${randomPart}.json`;

  const record = {
    schema_version: "hara_diagnostic_v1",
    source: "hara-site",
    received_at: iso,
    request: {
      cf_ray: request.headers.get("CF-Ray") || "",
      ip_country: request.headers.get("CF-IPCountry") || ""
    },
    payload
  };

  await env.DIAGNOSTICS_BUCKET.put(
    key,
    JSON.stringify(record, null, 2),
    {
      httpMetadata: {
        contentType: "application/json; charset=utf-8"
      },
      customMetadata: {
        source: "hara-site",
        schema: "hara_diagnostic_v1"
      }
    }
  );
}

async function handleDiagnostico(request, env) {
  let raw;

  try {
    raw = await request.json();
  } catch (_error) {
    return json({ ok: false, message: "JSON inválido." }, 400);
  }

  const turnstileToken = cleanText(raw.turnstileToken || raw["cf-turnstile-response"], 2048);

  if (!turnstileToken) {
    return json({
      ok: false,
      message: "Verificação de segurança obrigatória."
    }, 400);
  }

  const remoteIp = request.headers.get("CF-Connecting-IP") || undefined;
  const turnstile = await verifyTurnstile(
    turnstileToken,
    env.TURNSTILE_SECRET_KEY,
    remoteIp
  );

  if (!turnstile.success) {
    return json({
      ok: false,
      message: "Falha na verificação de segurança."
    }, 403);
  }

  const payload = {
    nome: cleanText(raw.nome, 120),
    email: cleanText(raw.email, 160),
    empresa: cleanText(raw.empresa, 160),
    cargo: cleanText(raw.cargo, 120),
    tipoEmpresa: cleanText(raw.tipoEmpresa, 120),
    colaboradores: cleanText(raw.colaboradores, 80),
    decisao: cleanText(raw.decisao, 120),
    sede: cleanText(raw.sede, 120),
    objetivo: cleanText(raw.objetivo, 160),
    urgencia: cleanText(raw.urgencia, 120),
    sponsor: cleanText(raw.sponsor, 120),
    documentacao: cleanText(raw.documentacao, 160),
    donoDados: cleanText(raw.donoDados, 160),
    maturidade: cleanText(raw.maturidade, 120),
    erp: cleanText(raw.erp, 120),
    crm: cleanText(raw.crm, 120),
    tech: cleanArray(raw.tech, 700),
    techOutro: cleanText(raw.techOutro, 240),
    sensibilidade: cleanArray(raw.sensibilidade, 700),
    compliance: cleanArray(raw.compliance, 700),
    maiorDor: cleanArray(raw.maiorDor, 700),
    arquitetura: cleanArray(raw.arquitetura, 700),
    dadosBase: cleanArray(raw.dadosBase, 700),
    dadosOutro: cleanText(raw.dadosOutro, 800),
    dores: cleanText(raw.dores, 1000),
    ia: cleanText(raw.ia, 1000),
    legalConfirm: Boolean(raw.legalConfirm)
  };

  const missing = missingRequired(payload);

  if (missing.length) {
    return json({
      ok: false,
      message: "Campos obrigatórios ausentes.",
      missing
    }, 400);
  }

  if (!isLikelyEmail(payload.email)) {
    return json({
      ok: false,
      message: "E-mail inválido."
    }, 400);
  }

  if (!payload.tech && !payload.techOutro) {
    return json({
      ok: false,
      message: "Informe ao menos uma tecnologia/plataforma ou preencha Outras tecnologias."
    }, 400);
  }

  const groupChecks = [
    ["sensibilidade", "Sensibilidade dos dados"],
    ["compliance", "Requisitos de compliance / governança"],
    ["maiorDor", "Onde está a maior dor"],
    ["arquitetura", "Arquitetura aceitável"],
    ["dadosBase", "Onde os dados / documentos vivem hoje"]
  ];

  const missingGroups = groupChecks
    .filter(([key]) => !payload[key])
    .map(([, label]) => label);

  if (missingGroups.length) {
    return json({
      ok: false,
      message: "Grupos obrigatórios ausentes.",
      missing: missingGroups
    }, 400);
  }

  if (!payload.legalConfirm) {
    return json({
      ok: false,
      message: "Confirmação jurídica obrigatória não informada."
    }, 400);
  }

  try {
    await saveDiagnosticToR2(env, payload, request);
  } catch (_error) {
    console.error("diagnostic_storage_failed");
    return json({
      ok: false,
      message: "Formulário validado, mas falhou ao armazenar o diagnóstico."
    }, 500);
  }

  return json({
    ok: true,
    message: "Formulário recebido e armazenado. Score e análise são processados internamente.",
    received_at: new Date().toISOString()
  });
}

async function observabilityPayload(payload) {
  const projected = publicObservabilityProjection(payload);
  const generatedAt = Date.parse(projected.generated_at_utc || "");
  const ageSeconds = Number.isFinite(generatedAt)
    ? Math.max(0, Math.floor((Date.now() - generatedAt) / 1000))
    : null;

  return {
    ...projected,
    freshness: {
      ...projected.freshness,
      seconds: ageSeconds,
      state:
        ageSeconds !== null &&
        ageSeconds <= Number(projected.freshness?.maximum_expected_seconds || 180)
          ? "fresh"
          : "stale"
    }
  };
}

async function handleObservabilityStatus(request, env) {
  const key = "observability/public/status/current.json";

  try {
    if (env.DIAGNOSTICS_BUCKET) {
      const object = await env.DIAGNOSTICS_BUCKET.get(key);

      if (object) {
        const payload = JSON.parse(await object.text());
        return json(await observabilityPayload(payload));
      }
    }
  } catch (_error) {
    // A static sanitized fallback remains available with the deployment.
  }

  const fallbackUrl = new URL("/observabilidade/status.json", request.url);
  const fallback = await env.ASSETS.fetch(new Request(fallbackUrl, request));

  if (!fallback.ok) {
    return json({
      ok: false,
      message: "Snapshot de observabilidade indisponível."
    }, 503);
  }

  try {
    const payload = await fallback.json();
    return json(await observabilityPayload(payload));
  } catch (_error) {
    return json({
      ok: false,
      message: "Snapshot de observabilidade inválido."
    }, 503);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (
      url.pathname === "/api/observabilidade/status" &&
      request.method === "GET"
    ) {
      return handleObservabilityStatus(request, env);
    }

    if (url.pathname === "/api/ping") {
      return json({
        ok: true,
        service: "hara-site",
        message: "Worker ativo"
      });
    }

    if (url.pathname === "/api/diagnostico" && request.method === "POST") {
      return handleDiagnostico(request, env);
    }

    if (url.pathname.startsWith("/api/")) {
      return json({
        ok: false,
        message: "Endpoint não encontrado."
      }, 404);
    }

    return env.ASSETS.fetch(request);
  }
};
