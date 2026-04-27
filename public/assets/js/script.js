document.addEventListener("DOMContentLoaded", function () {
  function cleanText(value, maxLength = 1000) {
    return String(value || "")
      .replace(/[<>{}[\]\\`]/g, "")
      .replace(/https?:\/\/\S+/gi, "[link removido]")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, maxLength);
  }

  function cleanTextarea(value, maxLength = 1000) {
    return String(value || "")
      .replace(/[<>{}[\]\\`]/g, "")
      .replace(/https?:\/\/\S+/gi, "[link removido]")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim()
      .slice(0, maxLength);
  }

  function getCheckedArray(name) {
    return Array.from(document.querySelectorAll(`input[name="${name}"]:checked`))
      .map((item) => item.value);
  }

  function hasValue(id) {
    const element = document.getElementById(id);
    return element && cleanText(element.value).length > 0;
  }

  function validateRequiredGroups(payload) {
    const missing = [];

    if (!payload.tech.length && !payload.techOutro) {
      missing.push("Tecnologias / plataformas ou Outras tecnologias");
    }

    if (!payload.sensibilidade.length) missing.push("Sensibilidade dos dados");
    if (!payload.compliance.length) missing.push("Requisitos de compliance / governança");
    if (!payload.maiorDor.length) missing.push("Onde está a maior dor");
    if (!payload.arquitetura.length) missing.push("Arquitetura aceitável");
    if (!payload.dadosBase.length) missing.push("Onde os dados / documentos vivem hoje");

    return missing;
  }

  function setupHeroCarousel() {
    const root =
      document.querySelector(".visual-card") ||
      document.querySelector(".hero-visual") ||
      document.querySelector(".hero-showcase");

    if (!root) return;

    const slides = [
      {
        image: "assets/images/hero-ia.png",
        title: "Percepção simplificada",
        description: "Muita gente imagina IA como um atalho direto entre dados e valor.",
        infographic: true,
        alt: "Percepção simplificada sobre IA: dados, IA e valor"
      },
      {
        image: "assets/images/hero-ia-realidade-sep.png",
        title: "Arquitetura operacional",
        description: "Valor real exige dados, engenharia, modelagem, restrições e operacionalização.",
        infographic: true,
        alt: "Fluxo real para gerar valor com IA: dados, ciência de dados, restrições e operacionalização"
      },
      {
        image: "assets/images/hara-logo-premium.webp",
        title: "IA como parte do fluxo",
        description: "IA amplifica estrutura. Não corrige desorganização.",
        infographic: false,
        alt: "H.A.R.A Labs"
      }
    ];

    root.classList.add("manual-hero-carousel", "hero-carousel-clean");

    // Ponto central da correção:
    // limpa somente o painel visual para remover duplicações antigas.
    root.innerHTML = "";

    const viewport = document.createElement("div");
    viewport.className = "hero-carousel-viewport";

    const slideElements = slides.map(function (slide, index) {
      const article = document.createElement("article");
      article.className = "slide";
      if (index === 0) article.classList.add("active");

      const frame = document.createElement("div");
      frame.className = "hero-slide-frame";

      const img = document.createElement("img");
      img.src = slide.image;
      img.alt = slide.alt;
      img.className = slide.infographic ? "is-infographic" : "is-logo";

      frame.appendChild(img);

      const copy = document.createElement("div");
      copy.className = "hero-slide-copy";

      const h3 = document.createElement("h3");
      h3.textContent = slide.title;

      const p = document.createElement("p");
      p.textContent = slide.description;

      copy.appendChild(h3);
      copy.appendChild(p);

      article.appendChild(frame);
      article.appendChild(copy);

      viewport.appendChild(article);
      return article;
    });

    const prevBtn = document.createElement("button");
    prevBtn.type = "button";
    prevBtn.className = "hero-nav prev";
    prevBtn.setAttribute("aria-label", "Slide anterior");
    prevBtn.textContent = "‹";

    const nextBtn = document.createElement("button");
    nextBtn.type = "button";
    nextBtn.className = "hero-nav next";
    nextBtn.setAttribute("aria-label", "Próximo slide");
    nextBtn.textContent = "›";

    viewport.appendChild(prevBtn);
    viewport.appendChild(nextBtn);

    const dotsWrap = document.createElement("div");
    dotsWrap.className = "dots";

    const dots = slides.map(function (_, index) {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.className = "dot";
      if (index === 0) dot.classList.add("active");
      dot.setAttribute("aria-label", `Ir para slide ${index + 1}`);
      dotsWrap.appendChild(dot);
      return dot;
    });

    root.appendChild(viewport);
    root.appendChild(dotsWrap);

    let current = 0;

    function showSlide(index) {
      current = index;

      slideElements.forEach(function (slide, i) {
        slide.classList.toggle("active", i === current);
      });

      dots.forEach(function (dot, i) {
        dot.classList.toggle("active", i === current);
      });
    }

    prevBtn.addEventListener("click", function () {
      showSlide((current - 1 + slides.length) % slides.length);
    });

    nextBtn.addEventListener("click", function () {
      showSlide((current + 1) % slides.length);
    });

    dots.forEach(function (dot, index) {
      dot.addEventListener("click", function () {
        showSlide(index);
      });
    });

    // Sem autoplay.
    showSlide(0);
  }

  function setupDiagnosticForm() {
    const form = document.getElementById("diagnosticForm");
    if (!form) return;

    form.addEventListener("submit", async function (event) {
      event.preventDefault();

      const data = new FormData(form);
      const submitButton = form.querySelector('button[type="submit"]');

      const requiredIds = [
        "nome", "email", "empresa", "cargo",
        "tipoEmpresa", "colaboradores", "decisao", "sede",
        "objetivo", "urgencia", "sponsor", "documentacao",
        "donoDados", "maturidade", "erp", "crm"
      ];

      const missingFields = requiredIds.filter((id) => !hasValue(id));

      if (missingFields.length) {
        alert("Preencha todos os campos obrigatórios antes de enviar.");
        return;
      }

      const legalConfirm = document.getElementById("legalConfirm");

      if (legalConfirm && !legalConfirm.checked) {
        alert("Confirme que o diagnóstico inicial não contém dados sensíveis ou confidenciais.");
        return;
      }

      const payload = {
        nome: cleanText(data.get("nome"), 120),
        email: cleanText(data.get("email"), 160),
        empresa: cleanText(data.get("empresa"), 160),
        cargo: cleanText(data.get("cargo"), 120),
        tipoEmpresa: cleanText(data.get("tipoEmpresa"), 120),
        colaboradores: cleanText(data.get("colaboradores"), 80),
        decisao: cleanText(data.get("decisao"), 120),
        sede: cleanText(data.get("sede"), 120),
        objetivo: cleanText(data.get("objetivo"), 160),
        urgencia: cleanText(data.get("urgencia"), 120),
        sponsor: cleanText(data.get("sponsor"), 120),
        documentacao: cleanText(data.get("documentacao"), 160),
        donoDados: cleanText(data.get("donoDados"), 160),
        maturidade: cleanText(data.get("maturidade"), 120),
        erp: cleanText(data.get("erp"), 120),
        crm: cleanText(data.get("crm"), 120),
        tech: getCheckedArray("tech"),
        techOutro: cleanText(data.get("techOutro"), 240),
        sensibilidade: getCheckedArray("sensibilidade"),
        compliance: getCheckedArray("compliance"),
        maiorDor: getCheckedArray("maiorDor"),
        arquitetura: getCheckedArray("arquitetura"),
        dadosBase: getCheckedArray("dadosBase"),
        dadosOutro: cleanTextarea(data.get("dadosOutro"), 800),
        dores: cleanTextarea(data.get("dores"), 1000),
        ia: cleanTextarea(data.get("ia"), 1000),
        legalConfirm: Boolean(legalConfirm && legalConfirm.checked),
        turnstileToken: cleanText(data.get("cf-turnstile-response"), 2048)
      };

      if (!payload.turnstileToken) {
        alert("Conclua a verificação de segurança antes de enviar.");
        return;
      }

      const missingGroups = validateRequiredGroups(payload);

      if (missingGroups.length) {
        alert("Preencha também: " + missingGroups.join(", "));
        return;
      }

      try {
        if (submitButton) {
          submitButton.disabled = true;
          submitButton.textContent = "Enviando...";
        }

        const response = await fetch("/api/diagnostico", {
          method: "POST",
          headers: {
            "content-type": "application/json"
          },
          body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (!response.ok || !result.ok) {
          throw new Error(result.message || "Falha ao enviar formulário.");
        }

        alert("Formulário enviado com sucesso. Obrigado.");
        form.reset();

        if (window.turnstile) {
          window.turnstile.reset();
        }
      } catch (error) {
        alert(error.message || "Não foi possível enviar agora. Tente contato direto por e-mail.");

        if (window.turnstile) {
          window.turnstile.reset();
        }
      } finally {
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.textContent = "Enviar formulário";
        }
      }
    });
  }

  setupHeroCarousel();
  setupDiagnosticForm();
});
