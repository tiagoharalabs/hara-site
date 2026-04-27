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

      const nome = cleanText(data.get("nome"), 120);
      const email = cleanText(data.get("email"), 160);
      const empresa = cleanText(data.get("empresa"), 160);
      const cargo = cleanText(data.get("cargo"), 120);
      const tipoEmpresa = cleanText(data.get("tipoEmpresa"), 120);
      const colaboradores = cleanText(data.get("colaboradores"), 80);
      const decisao = cleanText(data.get("decisao"), 120);
      const sede = cleanText(data.get("sede"), 120);
      const erp = cleanText(data.get("erp"), 120);
      const crm = cleanText(data.get("crm"), 120);
      const tech = getCheckedValues("tech");
      const techOutro = cleanText(data.get("techOutro"), 240);
      const dadosBase = getCheckedValues("dadosBase");
      const dadosOutro = cleanTextarea(data.get("dadosOutro"), 800);
      const dores = cleanTextarea(data.get("dores"), 1000);
      const ia = cleanTextarea(data.get("ia"), 1000);

      if (!nome || !email || !empresa) {
        alert("Por favor, preencha pelo menos nome, e-mail e empresa.");
        return;
      }

      const lines = [
        "Diagnóstico inicial H.A.R.A Labs",
        "",
        `Nome: ${nome}`,
        `E-mail: ${email}`,
        `Empresa: ${empresa}`,
        `Cargo / função: ${cargo || "Não informado"}`,
        `Perfil da empresa: ${tipoEmpresa || "Não informado"}`,
        `Quantidade de colaboradores: ${colaboradores || "Não informado"}`,
        `Origem das decisões de TI: ${decisao || "Não informado"}`,
        `País da sede / matriz: ${sede || "Não informado"}`,
        `ERP principal: ${erp || "Não informado"}`,
        `CRM principal: ${crm || "Não informado"}`,
        "",
        `Tecnologias / plataformas: ${tech || "Não informado"}`,
        `Outras tecnologias: ${techOutro || "Não informado"}`,
        "",
        `Bases / repositórios de dados: ${dadosBase || "Não informado"}`,
        "Outras fontes / contexto de dados:",
        dadosOutro || "Não informado",
        "",
        "Principais dores / sinais de fragilidade:",
        dores || "Não informado",
        "",
        "Uso atual ou interesse em IA:",
        ia || "Não informado"
      ];

      const subject = encodeURIComponent(`Diagnóstico inicial H.A.R.A Labs - ${empresa}`);
      const body = encodeURIComponent(lines.join("\n"));

      window.location.href =
        `mailto:contato@haralabs.com.br?subject=${subject}&body=${body}`;
    });
  }
})();
