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

  function getCheckedValues(name) {
    return Array.from(document.querySelectorAll(`input[name="${name}"]:checked`))
      .map((item) => item.value)
      .join(", ");
  }

  const form = document.getElementById("diagnosticForm");

  if (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();

      const data = new FormData(form);
      const legalConfirm = document.getElementById("legalConfirm");

      const nome = cleanText(data.get("nome"), 120);
      const email = cleanText(data.get("email"), 160);
      const empresa = cleanText(data.get("empresa"), 160);

      if (!nome || !email || !empresa) {
        alert("Por favor, preencha pelo menos nome, e-mail e empresa.");
        return;
      }

      if (legalConfirm && !legalConfirm.checked) {
        alert("Confirme que o diagnóstico inicial não contém dados sensíveis ou confidenciais.");
        return;
      }

      const lines = [
        "Diagnóstico inicial H.A.R.A Labs",
        "",
        "AVISO:",
        "O remetente confirmou que este diagnóstico inicial não contém credenciais, documentos internos, dados pessoais de terceiros, dados sensíveis detalhados ou informações confidenciais.",
        "",
        `Nome: ${nome}`,
        `E-mail: ${email}`,
        `Empresa: ${empresa}`,
        `Cargo / função: ${cleanText(data.get("cargo"), 120) || "Não informado"}`,
        `Perfil da empresa: ${cleanText(data.get("tipoEmpresa"), 120) || "Não informado"}`,
        `Quantidade de colaboradores: ${cleanText(data.get("colaboradores"), 80) || "Não informado"}`,
        `Origem das decisões de TI: ${cleanText(data.get("decisao"), 120) || "Não informado"}`,
        `País da sede / matriz: ${cleanText(data.get("sede"), 120) || "Não informado"}`,
        "",
        `Objetivo principal: ${cleanText(data.get("objetivo"), 160) || "Não informado"}`,
        `Urgência: ${cleanText(data.get("urgencia"), 120) || "Não informado"}`,
        `Patrocinador interno: ${cleanText(data.get("sponsor"), 120) || "Não informado"}`,
        `Documentação dos processos: ${cleanText(data.get("documentacao"), 160) || "Não informado"}`,
        `Dono dos dados: ${cleanText(data.get("donoDados"), 160) || "Não informado"}`,
        `Maturidade percebida: ${cleanText(data.get("maturidade"), 120) || "Não informado"}`,
        "",
        `ERP principal: ${cleanText(data.get("erp"), 120) || "Não informado"}`,
        `CRM principal: ${cleanText(data.get("crm"), 120) || "Não informado"}`,
        "",
        `Tecnologias / plataformas: ${getCheckedValues("tech") || "Não informado"}`,
        `Outras tecnologias: ${cleanText(data.get("techOutro"), 240) || "Não informado"}`,
        "",
        `Sensibilidade dos dados: ${getCheckedValues("sensibilidade") || "Não informado"}`,
        `Requisitos de compliance / governança: ${getCheckedValues("compliance") || "Não informado"}`,
        `Onde está a maior dor: ${getCheckedValues("maiorDor") || "Não informado"}`,
        `Arquitetura aceitável: ${getCheckedValues("arquitetura") || "Não informado"}`,
        "",
        `Bases / repositórios de dados: ${getCheckedValues("dadosBase") || "Não informado"}`,
        "Outras fontes / contexto de dados:",
        cleanTextarea(data.get("dadosOutro"), 800) || "Não informado",
        "",
        "Principais dores / sinais de fragilidade:",
        cleanTextarea(data.get("dores"), 1000) || "Não informado",
        "",
        "Uso atual ou interesse em IA:",
        cleanTextarea(data.get("ia"), 1000) || "Não informado"
      ];

      const subject = encodeURIComponent(`Diagnóstico inicial H.A.R.A Labs - ${empresa}`);
      const body = encodeURIComponent(lines.join("\n"));

      window.location.href =
        `mailto:contato@haralabs.com.br?subject=${subject}&body=${body}`;
    });
  }
})();
