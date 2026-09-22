const endpoint="/api/observabilidade/status";
const $=id=>document.getElementById(id);
function stateClass(value){
  const v=String(value||"").toLowerCase();
  if(["healthy","pass","up","ready"].some(x=>v.includes(x)))return"healthy";
  if(["critical","fail","down","blocked"].some(x=>v.includes(x)))return"critical";
  return"degraded";
}
function displayState(value){
  const v=String(value||"unknown").toLowerCase();
  if(["healthy","pass","up","ready"].some(x=>v.includes(x)))return"Saudável";
  if(["critical","fail","down","blocked"].some(x=>v.includes(x)))return"Crítico";
  if(["degraded","warning","warn"].some(x=>v.includes(x)))return"Atenção";
  if(["stale"].some(x=>v.includes(x)))return"Desatualizado";
  return"Indisponível";
}
function formatDate(value){
  if(!value)return"indisponível";
  const d=new Date(value);if(Number.isNaN(d.getTime()))return"indisponível";
  return new Intl.DateTimeFormat("pt-BR",{dateStyle:"short",timeStyle:"medium"}).format(d);
}
function formatFreshness(seconds){
  if(!Number.isFinite(seconds))return"não comprovado";
  const s=Math.max(0,Math.round(seconds));
  if(s<60)return`${s} s`;
  if(s<3600)return`${Math.round(s/60)} min`;
  if(s<86400)return`${Math.round(s/3600)} h`;
  return`${Math.round(s/86400)} dias`;
}
function renderSignals(signals={}){
  const entries=Object.entries(signals);
  $("signalsGrid").innerHTML=entries.length?entries.map(([key,s])=>{
    const label=s.label||key,value=s.display??s.value??"—",status=stateClass(s.state);
    return `<article class="obs-signal"><span class="label">${label}</span><strong>${value}</strong><p>${s.detail||""}</p><span class="obs-status-pill ${status}">${displayState(s.state)}</span></article>`;
  }).join(""):"<p>Nenhum sinal publicado.</p>";
}
function renderComponents(components=[]){
  $("componentsGrid").innerHTML=components.length?components.map(c=>{
    const status=stateClass(c.state);
    return `<article class="obs-component"><div class="obs-component-head"><h3>${c.name||"Componente"}</h3><span class="obs-status-pill ${status}">${displayState(c.state)}</span></div><p>${c.summary||"Sem resumo disponível."}</p></article>`;
  }).join(""):"<p>Nenhum componente publicado.</p>";
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
      label:"Snapshot público desatualizado",
      display:formatFreshness(derivedAge),
      detail:`A janela esperada é de ${formatFreshness(maxAge)}; o estado precisa ser lido como evidência histórica até nova coleta.`
    });
  }

  const componentHealthy=(payload.components||[]).filter(c=>stateClass(c.state)==="healthy");
  for(const c of componentHealthy){
    if(!healthy.some(x=>x.label===c.name)){
      healthy.push({label:c.name,display:"Saudável",detail:c.summary||""});
    }
  }
  if(stateClass(payload.governance?.state)==="healthy"){
    healthy.push({label:"Governança de publicação",display:"Saudável",detail:payload.governance?.summary||""});
  }

  const stale=Number.isFinite(derivedAge)&&Number.isFinite(maxAge)&&derivedAge>maxAge;
  const overallHealthy=stateClass(payload.overall_state)==="healthy";
  $("stateReasonsTitle").textContent=stale
    ?"Por que a evidência exige atenção?"
    :(overallHealthy?"O que sustenta o estado saudável?":"Por que o estado exige atenção?");
  $("healthyContextTitle").textContent=stale
    ?"O que estava saudável no último snapshot?"
    :(overallHealthy?"Sinais positivos atuais":"O que permanece saudável?");

  $("stateReasons").innerHTML=degraded.length
    ? degraded.map(x=>`<div class="obs-state-item"><span class="obs-state-dot degraded"></span><div><strong>${x.label}</strong><b>${x.display}</b><p>${x.detail}</p></div></div>`).join("")
    : `<div class="obs-state-item"><span class="obs-state-dot healthy"></span><div><strong>Operação estável nos sinais públicos selecionados</strong><p>${payload.overall_message||"Nenhum ponto de atenção atual foi publicado."}</p></div></div>`;

  $("stateHealthy").innerHTML=healthy.length
    ? healthy.slice(0,5).map(x=>`<div class="obs-state-item"><span class="obs-state-dot healthy"></span><div><strong>${x.label}</strong><b>${x.display}</b><p>${x.detail}</p></div></div>`).join("")
    : '<div class="obs-state-item"><span class="obs-state-dot neutral"></span><div><strong>Sem sinais saudáveis publicados</strong><p>Não há evidência suficiente para compor esta leitura.</p></div></div>';
}
function render(payload){
  const overall=payload.overall_state||"unknown";
  const publishedMs=Date.parse(payload.generated_at_utc||"");
  const derivedAge=Number.isFinite(publishedMs)?Math.max(0,(Date.now()-publishedMs)/1000):NaN;
  const maxAge=Number(payload.freshness?.maximum_expected_seconds);
  const stale=Number.isFinite(derivedAge)&&Number.isFinite(maxAge)&&derivedAge>maxAge;
  const klass=stale?"degraded":stateClass(overall);
  $("liveDot").className=`dot ${klass}`;
  $("liveLabel").textContent=stale?"Snapshot desatualizado":displayState(overall);
  $("overallState").textContent=displayState(overall);
  $("overallMessage").textContent=stale
    ? `O último snapshot público excedeu a janela esperada de atualização. ${payload.overall_message||""}`.trim()
    : (payload.overall_message||"Snapshot carregado.");
  $("generatedAt").textContent=formatDate(payload.generated_at_utc);
  $("freshness").textContent=formatFreshness(derivedAge);
  renderExecutiveSummary(payload,derivedAge,maxAge);
  const signals=payload.signals||{};
  $("coverageUp").textContent=signals.prometheus_targets?.up??"—";
  $("coverageTotal").textContent=signals.prometheus_targets?.total??"—";
  $("fleetUp").textContent=signals.fleet_online?.up??"—";
  $("fleetTotal").textContent=signals.fleet_online?.total??"—";
  $("fleetDetail").textContent=signals.always_on?.display
    ? `${signals.always_on.display} nós always-on disponíveis.`
    :"Disponibilidade agregada da frota.";
  $("incidentsCurrent").textContent=signals.current_incidents?.display??"—";
  $("incidentsDetail").textContent=signals.current_incidents?.detail||"Estado operacional corrente.";
  renderSignals(signals);renderComponents(payload.components||[]);
}
function failure(message){
  $("liveDot").className="dot critical";
  $("liveLabel").textContent="Snapshot indisponível";
  $("overallState").textContent="Indisponível";$("coverageUp").textContent="—";$("coverageTotal").textContent="—";$("fleetUp").textContent="—";$("fleetTotal").textContent="—";$("incidentsCurrent").textContent="—";
  $("overallMessage").textContent=message;
  $("stateReasons").innerHTML=`<div class="obs-state-item"><span class="obs-state-dot critical"></span><div><strong>Telemetria pública indisponível</strong><p>${message}</p></div></div>`;
  $("stateHealthy").innerHTML='<div class="obs-state-item"><span class="obs-state-dot neutral"></span><div><strong>Sem leitura positiva comprovável</strong><p>Aguardando um snapshot válido.</p></div></div>';
}
async function loadStatus(){
  $("refreshButton").disabled=true;
  try{
    const response=await fetch(`${endpoint}?t=${Date.now()}`,{cache:"no-store",headers:{accept:"application/json"}});
    if(!response.ok)throw new Error(`HTTP ${response.status}`);render(await response.json());
  }catch(error){failure(`Falha ao carregar o snapshot: ${error.message}`)}
  finally{$("refreshButton").disabled=false}
}
$("refreshButton").addEventListener("click",loadStatus);loadStatus();setInterval(loadStatus,60000);
