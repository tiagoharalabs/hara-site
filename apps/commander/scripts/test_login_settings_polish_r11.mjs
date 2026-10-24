import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";

const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const BEFORE="/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-advanced-direct-visible-r9-20261022/apps/commander";
const read=(base,p)=>fs.readFileSync(path.join(base,p),"utf8");
const html=read(ROOT,"public/index.html");
const js=read(ROOT,"public/app.js");
const css=read(ROOT,"public/ux-auth-settings-r11.css");
const oldHtml=read(BEFORE,"public/index.html");
const oldJs=read(BEFORE,"public/app.js");
const assertOnce=(text,token,label)=>assert.equal(text.split(token).length-1,1,label);
const segment=(input,start,end)=>input.slice(input.indexOf(start),input.indexOf(end,input.indexOf(start)));
const login=segment(html,'<section class="view auth-view" data-view="login"','<section class="view auth-view" data-view="signup"');
const signup=segment(html,'<section class="view auth-view" data-view="signup"','<section class="view app-view" data-view="dashboard"');
const settings=segment(html,'<section class="view app-view" data-view="security"','<section class="view app-view" data-view="help"');
assertOnce(html,'ux-auth-settings-r11.css?v=20261023-gold-luxe-r11',"CSS_BUST");
assertOnce(html,'app.js?v=20261023-revoke-click-r15',"JS_BUST");
assert.ok(!login.includes("auth-note"),"LOGIN_SECURITY_DISCLAIMER_PRESENT");
assert.ok(!signup.includes("auth-note"),"SIGNUP_NOTICE_PRESENT");
assert.ok(!login.includes("não recebe nem armazena"),"LOGIN_DISCLAIMER_REMAINED");
assert.ok(login.includes('identity-gateway-icon'),"LOGIN_PROVIDER_ICON_MISSING");
assert.ok(login.includes("Entrar com HARA Identity") && login.includes("Usar outra conta"),"AUTH_BUTTONS_MISSING");
assert.equal(html.match(/<p class="settings-card-subtitle">/g)?.length,5,"SUBTITLES_COUNT");
assert.equal(settings.match(/data-copy-local-mcp/g)?.length,1,"MCP_LOCAL_COPY_MISSING");
assert.equal(settings.match(/data-copy-simple-mcp/g)?.length,1,"MCP_REMOTE_COPY_MISSING");
assert.ok(settings.includes("data-refresh-service-health"),"HEALTH_REFRESH_MISSING");
const removedNote=`      document.querySelectorAll(".auth-note").forEach((node) => {
        node.textContent = authProviderConfigured
          ? "A autenticação acontece no HARA Identity. O HARA não recebe nem armazena sua senha."
          : "O provedor de identidade está temporariamente indisponível.";
      });
`;
const oldGate=`    if (protectedRoute) {
      showBanner("info", "Acesso protegido", "Entre com HARA Identity para acessar seu workspace.", "Entrar", () => startRemoteAuth(false));
      return;
    }`;
const newGate=`    if (protectedRoute) {
      // The login card already explains how to sign in; keep genuine auth errors visible.
      hideBanner();
      return;
    }`;
assert.ok(oldJs.includes(removedNote),"NOTE_PREIMAGE");
assert.ok(oldJs.includes(oldGate),"GATE_PREIMAGE");
assert.ok(!js.includes(removedNote),"LOGIN_NOTICE_REINTRODUCED");
assert.ok(js.includes(newGate),"AUTH_PROTECTED_ROUTE_R11_GUARD_LOST");
assert.ok(js.includes('async function confirmDeviceRevocation('),"R15_REVOCATION_MISSING");
assert.ok(js.includes('/api/portal/devices/history/clear'),"R13_HISTORY_CLEAR_MISSING");
assert.ok(js.includes('showBanner(\n          "warning"') || js.includes('"Login não concluído"'),"REAL_AUTH_ERRORS_REMOVED");
assert.match(css,/rgba\(237,168,49,.095\)/,"GOLD_GLOW_NOT_FOUND");
assert.match(css,/box-shadow: 0 5px 16px rgba\(235,173,51,.20\)/,"GOLD_BUTTON_GLOW_MISSING");
for(const selector of ["settings-connection-list > div","settings-card dl > div","\.session"])assert.ok(css.includes(selector.replaceAll("\\","")) || css.includes(selector),"SETTINGS_SCOPE_MISSING:"+selector);
assert.ok((css.match(/border: 0!important/g)||[]).length>=3,"INNER_DIVIDERS_NOT_REMOVED");
assert.ok(html.includes("Termos") && html.includes("Privacidade"),"LEGAL_LINKS_REMOVED");
assert.ok(oldHtml.includes('class="auth-note"'),"NO_BASELINE_SECURITY_NOTICE");
console.log("R11_LOGIN_SETTINGS_LAYOUT_REGRESSION_PASS=8_CASES");
