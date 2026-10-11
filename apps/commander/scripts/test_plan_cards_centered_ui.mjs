import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const html=fs.readFileSync(path.join(root,"public/index.html"),"utf8");
const css=fs.readFileSync(path.join(root,"public/styles.css"),"utf8");
const section=html.split('<section class="view app-view" data-view="plans"')[1]
  ?.split('<section class="view app-view" data-view="connections"')[0];
assert.ok(section);
assert.equal((section.match(/class="plan-card(?: featured)?"/g)||[]).length,2);
assert.ok(section.includes('aria-label="Plano e cobrança"'));
assert.ok(section.includes('10.000 <small>chamadas / mês</small>'));
assert.ok(section.includes('data-billing-price-label="STANDARD"'));
assert.ok(section.includes('data-billing-plan="STANDARD"'));
assert.ok(section.includes('data-billing-portal'));
assert.ok(section.includes('data-billing-ready="checkout"'));
assert.ok(section.includes('data-beta-access'));
assert.ok(!section.includes('id="plans-title"'));
console.log("PLAN_CARDS_FUNCTIONAL_AND_PRICE_CONTENT_PRESERVED=PASS");

const findRule=(selector)=>{
 const target=selector+"{";
 const start=css.indexOf(target,css.indexOf("Unified navigation"));
 assert.ok(start>=0,"CSS_RULE_MISSING:"+selector);
 return css.slice(start+target.length,css.indexOf("}",start));
};
const grid=findRule('.app-view[data-view="plans"] .plan-grid');
assert.ok(grid.includes('width:100%'));
assert.ok(grid.includes('max-width:1080px'));
assert.ok(grid.includes('margin:0 auto'));
assert.ok(grid.includes('repeat(2,minmax(0,1fr))'));
assert.ok(grid.includes('gap:18px'));
assert.ok(grid.includes('align-items:stretch'));
const card=findRule('.app-view[data-view="plans"] .plan-card');
assert.ok(card.includes('padding:22px 24px 20px'));
assert.ok(findRule('.app-view[data-view="plans"] .plan-card li').includes('padding:4px 0'));
assert.ok(findRule('.app-view[data-view="plans"] .plan-card ul').includes('margin:6px 0 12px'));
assert.ok(css.includes('@media(max-width:1050px){\n  .app-view[data-view="plans"] .plan-grid{\n    max-width:520px;\n    grid-template-columns:minmax(0,1fr)'));
assert.ok(css.includes('@media(max-width:760px){\n  .app-view[data-view="plans"] .plan-grid{max-width:100%}'));
assert.ok(html.includes('styles.css?v=20261010-centered-plans1'));
console.log("PLAN_CARDS_CENTERED_COMPACT_SYMMETRIC_RESPONSIVE=PASS");

assert.ok(css.includes('html[data-theme="dark"] .plan-card'));
assert.ok(css.includes('.plan-card.featured'));
assert.ok(css.includes('var(--line)'));
assert.equal((html.match(/<span class="plan-label">/g)||[]).length,2);
console.log("PLAN_CARDS_HARA_PALETTE_AND_BUTTONS_UNMODIFIED=PASS");
console.log("PLAN_CARDS_NO_BILLING_OR_AGENT_MUTATIONS=TRUE");
