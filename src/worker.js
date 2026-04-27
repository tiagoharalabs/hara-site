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
  if (!Array.isArray(value)) return cleanText(value, maxLength);

  return value
    .map((item) => cleanText(item, 80))
    .filter(Boolean)
    .join(", ")
    .slice(0, maxLength);
}

function isLikelyEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || "").trim());
}

async function handleDiagnostico(request) {
  let raw;

  try {
    raw = await request.json();
  } catch (_error) {
    return json({ ok: false, message: "JSON inválido." }, 400);
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
    erp: cleanText(raw.erp, 120),
    crm: cleanText(raw.crm, 120),
    tech: cleanArray(raw.tech, 700),
    techOutro: cleanText(raw.techOutro, 240),
    dadosBase: cleanArray(raw.dadosBase, 700),
    dadosOutro: cleanText(raw.dadosOutro, 800),
    dores: cleanText(raw.dores, 1000),
    ia: cleanText(raw.ia, 1000)
  };

  if (!payload.nome || !payload.email || !payload.empresa) {
    return json({
      ok: false,
      message: "Nome, e-mail e empresa são obrigatórios."
    }, 400);
  }

  if (!isLikelyEmail(payload.email)) {
    return json({
      ok: false,
      message: "E-mail inválido."
    }, 400);
  }

  return json({
    ok: true,
    message: "Diagnóstico recebido e sanitizado.",
    received_at: new Date().toISOString(),
    payload
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/ping") {
      return json({
        ok: true,
        service: "hara-site",
        message: "Worker ativo"
      });
    }

    if (url.pathname === "/api/diagnostico" && request.method === "POST") {
      return handleDiagnostico(request);
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
