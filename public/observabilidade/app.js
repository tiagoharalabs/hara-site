const endpoint="/api/observabilidade/status";
const $=id=>document.getElementById(id);
let lastStatusPayload=null;
let lastStatusFailure=null;
function obsT(source,params={}){
  return window.HARA_I18N?.t
    ? window.HARA_I18N.t(source,params)
    : String(source).replace(/\{(\w+)\}/g,(match,key)=>Object.hasOwn(params,key)?String(params[key]):match);
}
function obsLocale(){return window.HARA_I18N?.getLocale()||"pt-BR";}
function html(value){
  return String(value??"").replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
}
// Only this known editorial copy from the public snapshot is localized.
// Unknown names/text, received values, counts and IDs remain literal.
const publicCopy=new Set([
  "Telemetria atual indica operação estável nos sinais públicos selecionados.",
  "Sem drift verdadeiro, incidente atual ou revisão pendente nos sinais públicos selecionados.",
  "Telemetria canônica","Cobertura de observação","Frota observada","Incidentes atuais","Qualidade de dados",
  "Checagens públicas selecionadas sem inconsistências atuais.",
  "Frescor da telemetria","Idade da projeção operacional usada para compor este snapshot.",
  "Séries-alvo disponíveis na camada de observação agregada.",
  "Frota observada online","Disponibilidade agregada da frota observada, sem identificação individual.",
  "Núcleos always-on","Disponibilidade agregada dos nós com política always-on.",
  "Incidentes operacionais atuais após adjudicação; histórico preservado não entra neste contador.",
  "Serviços atuais unhealthy","Contagem atual de serviços classificados como unhealthy na projeção operacional.",
  "Inconsistências de dados selecionadas","Soma de inconsistências nas checagens públicas selecionadas de qualidade de dados.",
  "Governança de publicação"
]);
function snapshotText(value){
  const source=String(value??"");
  if(publicCopy.has(source))return obsT(source);
  let match;
  if((match=/^Projeção operacional atualizada; (\d+)\/(\d+) serviços essenciais observados ativos\.$/.exec(source)))
    return obsT("Projeção operacional atualizada; {up}/{total} serviços essenciais observados ativos.",{up:match[1],total:match[2]});
  if((match=/^(\d+) de (\d+) séries-alvo públicas selecionadas disponíveis\.$/.exec(source)))
    return obsT("{up} de {total} séries-alvo públicas selecionadas disponíveis.",{up:match[1],total:match[2]});
  if((match=/^(\d+)\/(\d+) nós observados online; (\d+)\/(\d+) nós always-on disponíveis\.$/.exec(source)))
    return obsT("{up}/{total} nós observados online; {alwaysUp}/{alwaysTotal} nós always-on disponíveis.",{up:match[1],total:match[2],alwaysUp:match[3],alwaysTotal:match[4]});
  if((match=/^(\d+) incidente\(s\) atual\(is\) e (\d+) serviço\(s\) atual\(is\) unhealthy\.$/.exec(source)))
    return obsT("{incidents} incidente(s) atual(is) e {services} serviço(s) atual(is) unhealthy.",{incidents:match[1],services:match[2]});
  return source;
}
function stateClass(value){
  const v=String(value||"").toLowerCase();
  if(["healthy","pass","up","ready"].some(x=>v.includes(x)))return"healthy";
  if(["critical","fail","down","blocked"].some(x=>v.includes(x)))return"critical";
  return"degraded";
}
function displayState(value){
  const v=String(value||"unknown").toLowerCase();
  if(["healthy","pass","up","ready"].some(x=>v.includes(x)))return obsT("Saudável");
  if(["critical","fail","down","blocked"].some(x=>v.includes(x)))return obsT("Crítico");
  if(["degraded","warning","warn"].some(x=>v.includes(x)))return obsT("Atenção");
  if(["stale"].some(x=>v.includes(x)))return obsT("Desatualizado");
  return obsT("Indisponível");
}
function formatDate(value){
  if(!value)return obsT("indisponível");
  const d=new Date(value);if(Number.isNaN(d.getTime()))return obsT("indisponível");
  return new Intl.DateTimeFormat(obsLocale(),{dateStyle:"short",timeStyle:"medium"}).format(d);
}
function formatFreshness(seconds){
  if(!Number.isFinite(seconds))return obsT("não comprovado");
  const s=Math.max(0,Math.round(seconds));
  if(s<60)return`${s} s`;
  if(s<3600)return`${Math.round(s/60)} min`;
  if(s<86400)return`${Math.round(s/3600)} h`;
  const days=Math.round(s/86400);
  return obsT(days===1?"{count} dia":"{count} dias",{count:days});
}
function renderSignals(signals={}){
  const entries=Object.entries(signals);
  $("signalsGrid").innerHTML=entries.length?entries.map(([key,s])=>{
    const label=s.label?snapshotText(s.label):key,value=s.display??s.value??"—",status=stateClass(s.state);
    return `<article class="obs-signal"><span class="label">${html(label)}</span><strong>${html(value)}</strong><p>${html(snapshotText(s.detail||""))}</p><span class="obs-status-pill ${status}">${html(displayState(s.state))}</span></article>`;
  }).join(""):`<p>${html(obsT("Nenhum sinal publicado."))}</p>`;
}
function renderComponents(components=[]){
  $("componentsGrid").innerHTML=components.length?components.map(c=>{
    const status=stateClass(c.state);
    return `<article class="obs-component"><div class="obs-component-head"><h3>${html(c.name?snapshotText(c.name):obsT("Componente"))}</h3><span class="obs-status-pill ${status}">${html(displayState(c.state))}</span></div><p>${html(c.summary?snapshotText(c.summary):obsT("Sem resumo disponível."))}</p></article>`;
  }).join(""):`<p>${html(obsT("Nenhum componente publicado."))}</p>`;
}

function renderExecutiveSummary(payload, derivedAge, maxAge){
  const signals=payload.signals||{};
  const degraded=[];
  const healthy=[];

  for(const [key,s] of Object.entries(signals)){
    const item={
      label:s.label||key,
      display:s.display??s.value??"—",
      detail:s.detail||""
    };
    if(stateClass(s.state)==="healthy") healthy.push(item);
    else degraded.push(item);
  }

  if(Number.isFinite(derivedAge)&&Number.isFinite(maxAge)&&derivedAge>maxAge){
    degraded.unshift({
      label:obsT("Snapshot público desatualizado"),
      display:formatFreshness(derivedAge),
      detail:obsT("A janela esperada é de {window}; o estado precisa ser lido como evidência histórica até nova coleta.",{window:formatFreshness(maxAge)})
    });
  }

  const componentHealthy=(payload.components||[]).filter(c=>stateClass(c.state)==="healthy");
  for(const c of componentHealthy){
    if(!healthy.some(x=>x.label===c.name)){
      healthy.push({label:c.name,display:obsT("Saudável"),detail:c.summary||""});
    }
  }
  if(stateClass(payload.governance?.state)==="healthy"){
    healthy.push({label:"Governança de publicação",display:obsT("Saudável"),detail:payload.governance?.summary||""});
  }

  const stale=Number.isFinite(derivedAge)&&Number.isFinite(maxAge)&&derivedAge>maxAge;
  const overallHealthy=stateClass(payload.overall_state)==="healthy";
  $("stateReasonsTitle").textContent=stale
    ?obsT("Por que a evidência exige atenção?")
    :(overallHealthy?obsT("O que sustenta o estado saudável?"):obsT("Por que o estado exige atenção?"));
  $("healthyContextTitle").textContent=stale
    ?obsT("O que estava saudável no último snapshot?")
    :(overallHealthy?obsT("Sinais positivos atuais"):obsT("O que permanece saudável?"));

  $("stateReasons").innerHTML=degraded.length
    ? degraded.map(x=>`<div class="obs-state-item"><span class="obs-state-dot degraded"></span><div><strong>${html(snapshotText(x.label))}</strong><b>${html(x.display)}</b><p>${html(snapshotText(x.detail))}</p></div></div>`).join("")
    : `<div class="obs-state-item"><span class="obs-state-dot healthy"></span><div><strong>${html(obsT("Operação estável nos sinais públicos selecionados"))}</strong><p>${html(payload.overall_message?snapshotText(payload.overall_message):obsT("Nenhum ponto de atenção atual foi publicado."))}</p></div></div>`;

  $("stateHealthy").innerHTML=healthy.length
    ? healthy.slice(0,5).map(x=>`<div class="obs-state-item"><span class="obs-state-dot healthy"></span><div><strong>${html(snapshotText(x.label))}</strong><b>${html(x.display)}</b><p>${html(snapshotText(x.detail))}</p></div></div>`).join("")
    : `<div class="obs-state-item"><span class="obs-state-dot neutral"></span><div><strong>${html(obsT("Sem sinais saudáveis publicados"))}</strong><p>${html(obsT("Não há evidência suficiente para compor esta leitura."))}</p></div></div>`;
}
function render(payload){
  const overall=payload.overall_state||"unknown";
  const publishedMs=Date.parse(payload.generated_at_utc||"");
  const derivedAge=Number.isFinite(publishedMs)?Math.max(0,(Date.now()-publishedMs)/1000):NaN;
  const maxAge=Number(payload.freshness?.maximum_expected_seconds);
  const stale=Number.isFinite(derivedAge)&&Number.isFinite(maxAge)&&derivedAge>maxAge;
  const klass=stale?"degraded":stateClass(overall);
  $("liveDot").className=`dot ${klass}`;
  $("liveLabel").textContent=stale?obsT("Snapshot desatualizado"):displayState(overall);
  $("overallState").textContent=displayState(overall);
  $("overallMessage").textContent=stale
    ? obsT("O último snapshot público excedeu a janela esperada de atualização. {message}",{message:snapshotText(payload.overall_message||"")}).trim()
    : (payload.overall_message?snapshotText(payload.overall_message):obsT("Snapshot carregado."));
  $("generatedAt").textContent=formatDate(payload.generated_at_utc);
  $("freshness").textContent=formatFreshness(derivedAge);
  renderExecutiveSummary(payload,derivedAge,maxAge);
  const signals=payload.signals||{};
  $("coverageUp").textContent=signals.prometheus_targets?.up??"—";
  $("coverageTotal").textContent=signals.prometheus_targets?.total??"—";
  $("fleetUp").textContent=signals.fleet_online?.up??"—";
  $("fleetTotal").textContent=signals.fleet_online?.total??"—";
  $("fleetDetail").textContent=signals.always_on?.display
    ? obsT("{count} nós always-on disponíveis.",{count:signals.always_on.display})
    :obsT("Disponibilidade agregada da frota.");
  $("incidentsCurrent").textContent=signals.current_incidents?.display??"—";
  $("incidentsDetail").textContent=signals.current_incidents?.detail?snapshotText(signals.current_incidents.detail):obsT("Estado operacional corrente.");
  renderSignals(signals);renderComponents(payload.components||[]);
}
function failure(errorMessage){
  const message=obsT("Falha ao carregar o snapshot: {error}",{error:errorMessage});
  $("liveDot").className="dot critical";
  $("liveLabel").textContent=obsT("Snapshot indisponível");
  $("overallState").textContent=obsT("Indisponível");$("coverageUp").textContent="—";$("coverageTotal").textContent="—";$("fleetUp").textContent="—";$("fleetTotal").textContent="—";$("incidentsCurrent").textContent="—";
  $("overallMessage").textContent=message;
  $("stateReasons").innerHTML=`<div class="obs-state-item"><span class="obs-state-dot critical"></span><div><strong>${html(obsT("Telemetria pública indisponível"))}</strong><p>${html(message)}</p></div></div>`;
  $("stateHealthy").innerHTML=`<div class="obs-state-item"><span class="obs-state-dot neutral"></span><div><strong>${html(obsT("Sem leitura positiva comprovável"))}</strong><p>${html(obsT("Aguardando um snapshot válido."))}</p></div></div>`;
}
function renderInitialStatus(){
  const labels={
    liveLabel:"Carregando estado",overallMessage:"Aguardando snapshot.",
    fleetDetail:"Disponibilidade agregada da frota.",incidentsDetail:"Estado operacional corrente.",
    stateReasonsTitle:"Leitura executiva.",healthyContextTitle:"O que permanece saudável?"
  };
  for(const [id,source] of Object.entries(labels))$(id).textContent=obsT(source);
  for(const id of ["stateReasons","stateHealthy"])$(id).innerHTML=`<p>${html(obsT("Aguardando snapshot."))}</p>`;
}
window.addEventListener("hara:languagechange",()=>{
  // Presentation only: retain polling, pending request and refresh-button state.
  if(lastStatusPayload)render(lastStatusPayload);else renderInitialStatus();
  if(lastStatusFailure!==null)failure(lastStatusFailure);
});
async function loadStatus(){
  $("refreshButton").disabled=true;
  try{
    const response=await fetch(`${endpoint}?t=${Date.now()}`,{cache:"no-store",headers:{accept:"application/json"}});
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    const payload=await response.json();
    render(payload);lastStatusPayload=payload;lastStatusFailure=null;
  }catch(error){lastStatusFailure=String(error.message);failure(lastStatusFailure)}
  finally{$("refreshButton").disabled=false}
}
renderInitialStatus();
$("refreshButton").addEventListener("click",loadStatus);loadStatus();setInterval(loadStatus,60000);
