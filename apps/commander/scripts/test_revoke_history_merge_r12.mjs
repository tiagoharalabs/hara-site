import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const prior='/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-login-settings-polish-r11-20261023/apps/commander';
const read=(base,p)=>fs.readFileSync(path.join(base,p),'utf8');
const html=read(root,'public/index.html');
const js=read(root,'public/app.js');
const worker=read(root,'src/worker.js');
const css=read(root,'public/layout-legibility-r7.css');
assert.ok(html.includes('ux-auth-settings-r11.css?v=20261023-gold-luxe-r11'));
assert.ok(html.includes('app.js?v=20261023-revoke-click-r15'));
assert.ok(html.includes('layout-legibility-r7.css?v=20261023-offline-revoke-r14'));
assert.ok(html.includes('data-confirm-revoke-device') === false); // rendered in JS
assert.ok(html.includes('data-confirm-history-clear'));
assert.ok(!html.includes('Mostrar ocultos') && !html.includes('Restaurar todos'));
assert.ok(html.includes('data-history-clear-error'));
assert.ok(js.includes('async function confirmDeviceRevocation('));
assert.ok(js.includes('async function confirmHistoryClear('));
assert.ok(js.includes('/api/portal/devices/history/clear'));
assert.ok(!js.includes('archivedRevokedDeviceIds') && !js.includes('saveHiddenRevokedIds'));
assert.ok(worker.includes('async function clearPortalDeviceHistory'));
assert.ok(worker.includes('LEFT JOIN commander_device_history h'));
assert.ok(worker.includes('"/api/portal/devices/history/clear"'));
assert.ok(css.includes('devices-history-confirm') && css.includes('device-history-error'));
assert.equal(read(root,'public/ux-auth-settings-r11.css'),read(prior,'public/ux-auth-settings-r11.css'));
assert.equal(read(root,'public/styles.css'),read(prior,'public/styles.css'));
assert.equal(read(root,'public/advanced-layout.css'),read(prior,'public/advanced-layout.css'));
assert.equal(read(root,'public/install/linux.sh'),read(prior,'public/install/linux.sh'));
assert.equal(read(root,'public/install/windows.ps1'),read(prior,'public/install/windows.ps1'));
// #163 deliberately adds one guarded minute cron. Require every other
// production config field to remain identical to the R11 security baseline.
const currentConfig=JSON.parse(read(root,'wrangler.jsonc'));
const priorConfig=JSON.parse(read(prior,'wrangler.jsonc'));
assert.deepEqual(currentConfig.triggers.crons,['17 * * * *','* * * * *']);
assert.deepEqual({...currentConfig,triggers:{...currentConfig.triggers,
  crons:priorConfig.triggers.crons}},priorConfig);
console.log('R14_REVOKE_UI_AUTH_BRANDING_AND_INSTALLERS_REGRESSION_PASS=21_CHECKS');
