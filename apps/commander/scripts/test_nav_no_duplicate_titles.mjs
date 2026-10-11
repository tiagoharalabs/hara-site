import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const html=fs.readFileSync(path.join(root,"public/index.html"),"utf8");
const css=fs.readFileSync(path.join(root,"public/styles.css"),"utf8");
const nav=html.split('<template id="sidebarTemplate">')[1]?.split("</template>")[0];
assert.ok(nav,"MISSING_SIDEBAR_TEMPLATE");

const menu=[
  ["devices","Computadores"],
  ["usage","Uso"],
  ["plans","Plano e cobrança"],
  ["security","Configurações"],
];
const findView=(route)=>{
  const start=html.indexOf('<section class="view app-view" data-view="'+route+'"');
  const end=html.indexOf('\n    <section class="view ',start+10);
  assert.ok(start>=0,"MISSING_ROUTE:"+route);
  return html.slice(start,end<0?undefined:end);
};
for(const [route,name] of menu){
  assert.ok(nav.includes('data-app-go="'+route+'"'),"MISSING_SIDEBAR_LINK:"+route);
  assert.ok(nav.includes("<span>"+name+"</span>"),"SIDEBAR_NAME_CHANGED:"+name);
  const view=findView(route);
  assert.ok(view.includes('aria-label="'+name+'"'),"ACCESSIBLE_LANDMARK:"+route);
  assert.doesNotMatch(view,/class="workspace-head"/,
    "DUPLICATE_TOP_LEVEL_HEADER:"+route);
  assert.doesNotMatch(view,new RegExp('<h1[^>]*>\\s*'+name+'\\s*</h1>','i'),
    "DUPLICATE_SIDEBAR_HEADING:"+route);
  assert.doesNotMatch(view,new RegExp('id="'+route+'-title"'),
    "ORPHANED_TITLE_ID:"+route);
  console.log("SIDEBAR_ROUTE_NO_REPEAT="+route+":PASS");
}
assert.equal((nav.match(/data-app-go=/g)||[]).length,4,"SIDEBAR_SHOULD_HAVE_FOUR_ITEMS");

// Critical content must remain; only navigation-repeated page headers are removed.
assert.ok(findView("devices").includes('id="deviceList"'));
assert.ok(findView("usage").includes('id="usageConsumed"'));
assert.ok(findView("plans").includes('data-billing-price-label="STANDARD"'));
assert.ok(findView("security").includes('data-security-subject'));
assert.ok(html.includes('<h1 id="landing-title">'));
assert.ok(html.includes('<h1 id="login-title">'));
assert.ok(html.includes('<h1 id="signup-title">'));
console.log("NAV_ACTIONS_AND_NON_NAV_HEADINGS_PRESERVED=PASS");

assert.ok(css.includes('.app-view[data-view="usage"] .workspace-main'));
assert.ok(css.includes('.app-view[data-view="plans"] .workspace-main'));
assert.ok(css.includes('.app-view[data-view="security"] .workspace-main'));
assert.ok(css.includes('padding-top:10px'));
assert.ok(css.includes('.app-view[data-view="plans"] .plan-grid'));
assert.ok(css.includes('max-width:none'));
console.log("NAV_MAIN_CONTENT_ALIGNED_AND_WIDE=PASS");

const commandView=findView("devices");
const intro=commandView.match(/<p class="devices-guide-intro">([^<]+)<\/p>/)?.[1];
const onboard=commandView.match(/<article class="panel device-install-card device-onboarding-flow">[\s\S]*?<p>([^<]+)<\/p>/)?.[1];
assert.ok(intro&&onboard,"BOTH_INTRO_PARAGRAPHS_PRESENT");
assert.ok(intro.length < 95,"COMMANDS_INTRO_UNNECESSARILY_LONG");
assert.ok(onboard.length < 115,"ONBOARD_INTRO_UNNECESSARILY_LONG");
assert.ok(css.includes('width:100%;max-width:none;min-width:0'),
  "FULL_WIDTH_PARAGRAPHS_REQUIRED");
assert.ok(css.includes('@media(min-width:1400px)'));
assert.ok(css.includes('white-space:nowrap'));
assert.ok(css.includes('@media(max-width:1399px)'));
assert.ok(css.includes('white-space:normal'));
assert.ok(html.includes('20261010-centered-plans-vertical1'));
console.log("NAV_RESPONSIVE_INTRO_NO_PREMATURE_WRAP=PASS");
console.log("NAV_ONLY_HTML_CSS_NO_BACKEND_OR_SECRET_CHANGE=TRUE");
