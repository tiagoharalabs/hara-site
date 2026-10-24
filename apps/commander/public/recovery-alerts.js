// HARA recovery inbox: owner/admin portal, opt-in Worker contract only.
// No customer payload, bearer or local storage; explicit human ACK only.
(() => {
  "use strict";
  const root=document.getElementById("mainContent");
  if (!root || !window.fetch) return;
  const box=document.createElement("section");
  box.className="commander-recovery-inbox";
  box.setAttribute("aria-label","Alertas de recuperação do Commander");
  box.hidden=true;
  const title=document.createElement("h2");
  title.textContent="Alertas de recuperação";
  const hint=document.createElement("p");
  hint.textContent="Eventos registrados na plataforma. Reconhecer um alerta não significa que uma notificação externa foi entregue.";
  const list=document.createElement("ul");
  list.className="commander-recovery-alert-list";
  box.append(title,hint,list);
  root.prepend(box);
  let busy=false, epoch=0, active=false, wasAuthenticated=false, unavailable=false;
  const safeState={STALLED:"Travamento detectado",RECOVERING:"Recuperação em andamento",
    RECOVERED:"Recuperado",DEGRADED:"Conectividade degradada"};
  function clear() {
    epoch++;
    active=false;
    wasAuthenticated=false;
    unavailable=false;
    box.hidden=true;
    list.replaceChildren();
  }
  function authenticated() {
    return document.body.classList.contains("session-authenticated")
      && !document.querySelector("[data-auth-session]")?.hidden;
  }
  async function refresh() {
    if (!authenticated()) {if (wasAuthenticated) clear();return;}
    wasAuthenticated=true;
    if (document.hidden || unavailable || busy) return;
    busy=true;
    const current=epoch;
    try {
      const response=await fetch("/api/portal/recovery-events",{credentials:"same-origin",cache:"no-store"});
      if (current!==epoch || !authenticated()) return;
      if (response.status===404 || response.status===403) {
        box.hidden=true;list.replaceChildren();unavailable=true;return;
      }
      if (response.status===401) {clear();return;}
      if (!response.ok) return;
      const payload=await response.json();
      if (current!==epoch || !authenticated()
          || payload.schema!=="hara.commander.recovery-inbox.v1"
          || !Array.isArray(payload.events)) return;
      const rows=payload.events.filter(row=>!row.portal_ack_at_utc).slice(0,20);
      const next=document.createDocumentFragment();
      for (const alert of rows) {
        if (!/^HARA-REC-[0-9a-f]{48}$/.test(String(alert.event_id||""))) continue;
        const li=document.createElement("li");
        const description=document.createElement("span");
        const state=safeState[alert.event_state]||"Evento do Commander";
        // Untrusted fields remain text, never HTML.
        description.textContent=state+" — "+String(alert.device_id||"Dispositivo")+" · "+String(alert.persisted_at_utc||"");
        const button=document.createElement("button");
        button.type="button";
        button.textContent="Reconhecer";
        button.dataset.eventId=alert.event_id;
        li.append(description,button);
        next.append(li);
      }
      list.replaceChildren(next);
      box.hidden=list.children.length===0;
      active=true;
    } catch (_error) {
      // Network/auth errors cannot imply acknowledgement or remote delivery.
    } finally {busy=false;}
  }
  box.addEventListener("click",async event=>{
    const button=event.target.closest("button[data-event-id]");
    if (!button || button.disabled || !authenticated()) return;
    button.disabled=true;
    const id=button.dataset.eventId;
    const before=epoch;
    try {
      const response=await fetch("/api/portal/recovery-events/ack",{
        method:"POST",credentials:"same-origin",cache:"no-store",
        headers:{"content-type":"application/json"},
        body:JSON.stringify({event_id:id}),
      });
      const result=await response.json();
      if (before===epoch && authenticated() && response.ok
          && result.ack==="PORTAL_ACKNOWLEDGED" && result.event_id===id) {
        await refresh();
      } else if (before===epoch) button.disabled=false;
    } catch (_error) {if (before===epoch) button.disabled=false;}
  });
  const observer=new MutationObserver(()=>{
    if (!authenticated()) {if (wasAuthenticated || active) clear();return;}
    void refresh();
  });
  observer.observe(document.body,{attributes:true,attributeFilter:["class"]});
  document.addEventListener("visibilitychange",()=>{if (!document.hidden) void refresh();});
  setInterval(()=>void refresh(),60000);
  if (authenticated()) void refresh();
})();
