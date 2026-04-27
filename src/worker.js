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

  return json({
    ok: true,
    message: "Formulário recebido e sanitizado. Score e análise são processados internamente.",
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
