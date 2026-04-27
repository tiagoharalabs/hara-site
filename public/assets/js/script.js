(function () {
  const slides = Array.from(document.querySelectorAll(".slide"));
  const dots = Array.from(document.querySelectorAll(".dot"));
  let current = 0;
  let intervalId = null;

  function showSlide(index) {
    slides.forEach((slide, i) => slide.classList.toggle("active", i === index));
    dots.forEach((dot, i) => dot.classList.toggle("active", i === index));
    current = index;
  }

  function nextSlide() {
    if (!slides.length) return;
    showSlide((current + 1) % slides.length);
  }

  function startSlider() {
    if (slides.length <= 1) return;
    intervalId = setInterval(nextSlide, 4500);
  }

  function resetSlider() {
    if (intervalId) clearInterval(intervalId);
    startSlider();
  }

  dots.forEach((dot, index) => {
    dot.addEventListener("click", function () {
      showSlide(index);
      resetSlider();
    });
  });

  showSlide(0);
  startSlider();

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

  const form = document.getElementById("diagnosticForm");

  if (form) {
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
        legalConfirm: Boolean(legalConfirm && legalConfirm.checked)
      };

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
      } catch (error) {
        alert(error.message || "Não foi possível enviar agora. Tente contato direto por e-mail.");
      } finally {
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.textContent = "Enviar formulário";
        }
      }
    });
  }
})();
