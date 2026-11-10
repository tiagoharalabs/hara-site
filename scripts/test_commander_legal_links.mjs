import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = name => fs.readFileSync(path.join(root, 'public', name), 'utf8');
const home = read('index.html');
const products = read('produtos/index.html');
const commander = read('commander/index.html');
const specific = read('commander/termos/index.html');
const legal = read('legal/index.html');
const general = read('legal/termos/index.html');
const privacy = read('legal/privacidade/index.html');
const css = read('assets/css/legal.css');
const rawCatalog = read('assets/js/i18n-catalog.js');
const catalog = JSON.parse(rawCatalog.slice(rawCatalog.indexOf('=')+1).trim().replace(/;\s*$/, ''));

assert.match(home, /href="\/commander\/"[^>]*><span[^>]*data-i18n="s307"/, 'HOME_PRODUCT_LINK');
assert.match(products, /href="\/commander\/"[^>]*><span[^>]*data-i18n="cmd-back-product"/, 'PORTFOLIO_PRODUCT_LINK');
assert.match(commander, /<title>Hara Commander \| HARA Labs<\/title>/, 'CLEAN_PRODUCT_TITLE');
assert.doesNotMatch(home, /Conhecer o produto/, 'CONSISTENT_PRODUCT_CTA');
assert.match(legal, /href="\/legal\/termos\/"[\s\S]*?href="\/legal\/privacidade\/"[\s\S]*?href="\/commander\/termos\/"/, 'GENERAL_AND_PRODUCT_SCOPE');
assert.match(specific, /href="\/legal\/termos\/"/, 'SPECIFIC_LINKS_GENERAL');
assert.match(general, /href="\/commander\/termos\/"/, 'GENERAL_LINKS_SPECIFIC');
assert.match(privacy, /href="\/commander\/termos\/"/, 'PRIVACY_LINKS_SPECIFIC');
assert.match(commander, /href="\/legal\/privacidade\/"/, 'COMMANDER_PRIVACY_LINK');
assert.doesNotMatch(css, /\.legal-kicker:before\s*\{/, 'NO_DECORATIVE_LEGAL_DASH');
for (const page of [commander, specific, general, privacy, legal]) {
  assert.doesNotMatch(page, /<title>[^<]*[—·][^<]*<\/title>/, 'NO_DASH_IN_PAGE_TITLE');
  assert.match(page, /data-i18n-page-title="[^"]+"/, 'LOCALIZED_PAGE_TITLE');
}
for (const key of ['cmd-general-terms','cmd-legal-product','cmd-legal-open','cmd-specific-scope','cmd-privacy-scope','cmd-legal-docs-nav']) {
  assert.ok(catalog.pt[key] && catalog.en[key], 'BILINGUAL_' + key);
}
const previewPath='assets/images/hara-commander-commercial-hero-20261110.webp';
assert.ok(fs.existsSync(path.join(root,'public',previewPath)),'PRODUCT_SCREENSHOT_ASSET');
assert.doesNotMatch(css,/commander-product-mark/,'NO_ORPHANED_MASCOT_STYLES');
for(const page of [home,commander]){
  assert.match(page,/class="commander-product-preview"/,'REAL_PRODUCT_PREVIEW');
  assert.match(page,/src="\/assets\/images\/hara-commander-commercial-hero-20261110.webp"/,'COMMERCIAL_HERO_SOURCE');
  assert.doesNotMatch(page,/class="commander-product-mark"/,'NO_OLD_MASCOT_CARD');
}
for(const key of ['cmd-preview-open','cmd-preview-alt','cmd-preview-close','cmd-preview-dialog'])assert.ok(catalog.pt[key]&&catalog.en[key],'BILINGUAL_PREVIEW_'+key);
for(const page of [home,commander]){
  assert.match(page,/href="#commander-preview-full"/,'IN_PAGE_PREVIEW');
  assert.match(page,/id="commander-preview-full"/,'PREVIEW_OVERLAY');
  assert.doesNotMatch(page,/target="_blank"[^>]*href="[^"]*\.webp"/,'NO_RAW_IMAGE_TAB');
  assert.match(page,/favicon-32\.png\?v=20261110-hero2/,'FAVICON_LINK');
}
assert.doesNotMatch(css,/\.commander-demo-grid \}/,'NO_MALFORMED_CSS');
console.log('HARA_SITE_LEGAL_NAVIGATION=PASS; COMMANDER_LINKS=PASS; TERMS_DISTINCT=PASS; PT_EN=PASS');
