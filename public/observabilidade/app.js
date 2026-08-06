const endpoint="/api/observabilidade/status";
const $=id=>document.getElementById(id);
function stateClass(value){
  const v=String(value||"").toLowerCase();
  if(["healthy","pass","up","ready"].some(x=>v.includes(x)))return"healthy";
  if(["critical","fail","down","blocked"].some(x=>v.includes(x)))return"critical";
  return"degraded";
}
function displayState(value){
  const v=String(value||"unknown").replaceAll("_"," ");
  return v.charAt(0).toUpperCase()+v.slice(1);
}
function formatDate(value){
  if(!value)return"indisponível";
  const d=new Date(value);if(Number.isNaN(d.getTime()))return"indisponível";
  return new Intl.DateTimeFormat("pt-BR",{dateStyle:"short",timeStyle:"medium"}).format(d);
}
function formatFreshness(seconds){
  if(!Number.isFinite(seconds))return"não comprovado";
  return seconds<60?`${Math.max(0,Math.round(seconds))} s`:`${Math.round(seconds/60)} min`;
}
function renderSignals(signals={}){
  const entries=Object.entries(signals);
  $("signalsGrid").innerHTML=entries.length?entries.map(([key,s])=>{
    const label=s.label||key,value=s.display??s.value??"—",status=stateClass(s.state);
    return `<article class="signal"><span class="label">${label}</span><strong>${value}</strong><p>${s.detail||""}</p><span class="status-pill ${status}">${displayState(s.state)}</span></article>`;
  }).join(""):"<p>Nenhum sinal publicado.</p>";
}
function renderComponents(components=[]){
  $("componentsGrid").innerHTML=components.length?components.map(c=>{
    const status=stateClass(c.state);
    return `<article class="component"><div class="component-head"><h3>${c.name||"Componente"}</h3><span class="status-pill ${status}">${displayState(c.state)}</span></div><p>${c.summary||"Sem resumo disponível."}</p></article>`;
  }).join(""):"<p>Nenhum componente publicado.</p>";
}
function render(payload){
  const overall=payload.overall_state||"unknown",klass=stateClass(overall);
  $("liveDot").className=`dot ${klass}`;$("liveLabel").textContent=`Estado ${displayState(overall)}`;
  $("overallState").textContent=displayState(overall);$("overallMessage").textContent=payload.overall_message||"Snapshot carregado.";
  $("generatedAt").textContent=formatDate(payload.generated_at_utc);$("freshness").textContent=formatFreshness(payload.freshness?.seconds);
  const signals=payload.signals||{};
  $("targetsUp").textContent=signals.targets?.up??"—";$("targetsTotal").textContent=signals.targets?.total??"—";
  $("observerState").textContent=displayState(signals.observer?.state);$("observerDetail").textContent=signals.observer?.detail||"Telemetria sem detalhe.";
  $("governanceState").textContent=displayState(payload.governance?.state);$("governanceDetail").textContent=payload.governance?.summary||"Governança sem detalhe.";
  renderSignals(signals);renderComponents(payload.components||[]);
}
function failure(message){$("liveDot").className="dot critical";$("liveLabel").textContent="Snapshot indisponível";$("overallState").textContent="Indisponível";$("overallMessage").textContent=message;}
async function loadStatus(){
  $("refreshButton").disabled=true;
  try{
    const response=await fetch(`${endpoint}?t=${Date.now()}`,{cache:"no-store",headers:{accept:"application/json"}});
    if(!response.ok)throw new Error(`HTTP ${response.status}`);render(await response.json());
  }catch(error){failure(`Falha ao carregar o snapshot: ${error.message}`)}
  finally{$("refreshButton").disabled=false}
}
$("refreshButton").addEventListener("click",loadStatus);loadStatus();setInterval(loadStatus,60000);
