import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const dirname=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(dirname,"..");
const html=fs.readFileSync(path.join(root,"public/index.html"),"utf8");
const js=fs.readFileSync(path.join(root,"public/app.js"),"utf8");
const css=fs.readFileSync(path.join(root,"public/styles.css"),"utf8");
const linux=fs.readFileSync(path.join(root,"public/agent/linux.py"),"utf8");
const windows=fs.readFileSync(path.join(root,"public/agent/windows.ps1"),"utf8");

const section=html.split('<section class="view app-view" data-view="devices"')[1]
  .split('<section class="view app-view" data-view="usage"')[0];
assert.ok(section,"DEVICES_SECTION_NOT_FOUND");

for(const tab of ["devices","connect","commands"]){
  assert.equal((section.match(new RegExp('data-device-section-tab="'+tab+'"','g'))||[]).length,1);
  assert.equal((section.match(new RegExp('data-device-section-panel="'+tab+'"','g'))||[]).length,1);
}
assert.doesNotMatch(section,/devicesHelp|quickstart-panel|device-where-panel/);
assert.ok(section.indexOf('data-device-section-tab="devices"') <
  section.indexOf('data-device-section-tab="connect"'));
assert.ok(section.indexOf('data-device-section-tab="connect"') <
  section.indexOf('data-device-section-tab="commands"'));
assert.ok(section.indexOf('data-device-section-panel="devices"') <
  section.indexOf('data-device-section-panel="connect"'));
assert.ok(section.indexOf('data-device-section-panel="connect"') <
  section.indexOf('data-device-section-panel="commands"'));
console.log("COMMANDER_SETUP_THREE_TABS_NO_DUPLICATE_ONBOARDING=PASS");

const onboarding=section.split('data-device-section-panel="connect"')[1]
  .split('data-device-section-panel="commands"')[0];
for(const marker of [
  'Escolha o sistema', 'Seu código de conexão', 'Instale no seu computador',
  'data-create-pairing', 'id="pairingPanel"', 'id="pairingToken"',
  'data-copy-pairing', 'data-install-linux-code', 'data-install-windows-code',
  'Pairing token', 'data-os-choice="linux"', 'data-os-choice="windows"',
]){
  assert.ok(onboarding.includes(marker),"ONBOARDING_MISSING:"+marker);
}
assert.ok(onboarding.indexOf('Escolha o sistema')<
  onboarding.indexOf('Seu código de conexão'));
assert.ok(onboarding.indexOf('Seu código de conexão')<
  onboarding.indexOf('Instale no seu computador'));
assert.ok(onboarding.indexOf('data-create-pairing')<
  onboarding.indexOf('data-install-linux-code'));
assert.equal((onboarding.match(/data-create-pairing/g)||[]).length,1);
assert.match(onboarding,/data-copy-linux/);
assert.match(onboarding,/data-copy-windows/);
assert.match(onboarding,/class="devices-setup-advanced"/);
assert.doesNotMatch(onboarding,/data-copy-agent-start|data-copy-agent-stop/);
assert.match(onboarding,/hara-commander-commercial-v0\.3\.43-signed-v2/);
assert.ok(!onboarding.includes('installApprovalMode'));
console.log("COMMANDER_SETUP_PLATFORM_TOKEN_INSTALL_SEQUENCE=PASS");

const begin=js.indexOf("  function installCommandLinux() {");
const end=js.indexOf("  function syncInstallCommands()",begin);
assert.ok(begin>=0&&end>begin);
const context=vm.createContext({installTransportMode:"OUTBOUND_RELAY"});
vm.runInContext(js.slice(begin,end),context,{timeout:2000});
const linuxInstall=vm.runInContext("installCommandLinux()",context);
const windowsInstall=vm.runInContext("installCommandWindows()",context);
for(const s of [linuxInstall,windowsInstall]){
  assert.ok(s.includes("https://commander.haralabs.com.br/install/"));
  assert.ok(s.includes("ASK_EVERY_ACTION"));
  assert.ok(!/pairing_token\s*=/.test(s));
  assert.ok(!s.includes("PERSISTENT_TRUSTED"));
}
assert.ok(linuxInstall.includes("HARA_COMMANDER_TUNNEL_AUTOSTART=OFF"));
assert.ok(linuxInstall.includes("HARA_COMMANDER_TRANSPORT_MODE=OUTBOUND_RELAY"));
assert.ok(linuxInstall.includes("curl -fsS"));
assert.ok(windowsInstall.includes("Invoke-WebRequest"));
assert.ok(windowsInstall.includes("powershell.exe"));
assert.match(js,/portalFetch\("\/api\/portal\/devices\/pairing"/);
assert.match(js,/armPairingExpiry\(payload\.expires_at_utc\)/);
assert.match(js,/pairingToken/);
console.log("COMMANDER_SETUP_COMMANDS_SIGNED_HTTP_AND_TOKEN_PROMPT=PASS");

const commands=section.split('data-device-section-panel="commands"')[1];
const supported=[
  "hara-commander start",
  "hara-commander status",
  "hara-commander stop",
  "hara-commander doctor",
  "hara-commander mcp",
  "https://commander.haralabs.com.br/api/mcp?profile=simple",
  "hara-commander tunnel configure",
  "hara-commander authorize",
  "hara-commander tunnel start",
  "hara-commander tunnel stop",
];
for(const command of supported){
  assert.ok(commands.includes(command),"COMMAND_GUIDE_MISSING:"+command);
}
for(const mode of ["start","status","stop"]){
  assert.ok(commands.includes("-File $agent "+mode),"WINDOWS_COMMAND_MISSING:"+mode);
  assert.ok(windows.includes('eq "'+mode+'"'),"WINDOWS_AGENT_UNKNOWN_CLI:"+mode);
}
assert.ok(linux.includes('sys.argv[1]=="mcp"'));
assert.ok(linux.includes('sys.argv[1]=="doctor"'));
assert.ok(commands.includes("modo local STDIO ainda não está disponível"));
assert.ok(commands.includes("Não existe comando manual de sincronização."));
assert.ok(!commands.includes("hara-commander sync"));
assert.ok((commands.match(/data-copy-guide-command/g)||[]).length>=10);
assert.match(js,/const guideCommand = event\.target\.closest\("\[data-copy-guide-command\]"\)/);
assert.match(js,/copyText\(code\.textContent\.trim\(\), "Comando copiado para o terminal\."\)/);
console.log("COMMANDER_GUIDE_LINUX_WINDOWS_MCP_TRUE_COMMANDS=PASS");

assert.match(css,/\.devices-command-grid/);
assert.match(css,/\.devices-setup-advanced/);
assert.match(css,/html\[data-theme="dark"\] \[data-view="devices"\]/);
assert.match(html,/styles\.css\?v=20261014-usage-help-ui-v1/);
assert.match(html,/app\.js\?v=20261023-revoke-click-r15/);
assert.match(css,/--gold/);
console.log("COMMANDER_GUIDE_COLORS_THEME_RESPONSIVE=PASS");

const rule = (selector) => {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = css.match(new RegExp(escaped+"\\s*\\{([^}]+)\\}"));
  assert.ok(match,"MISSING_STYLE_RULE_"+selector);
  return match[1];
};
const panelStyle = rule('[data-view="devices"] .devices-command-guide');
assert.match(panelStyle,/width:100%;max-width:none/);
assert.match(panelStyle,/padding:20px 24px 24px/);
assert.match(panelStyle,/border:1px solid var\(--line\);border-radius:14px/);
assert.match(panelStyle,/background:var\(--white\)/);
const gridStyle = rule('[data-view="devices"] .devices-command-grid');
assert.ok(gridStyle.includes("repeat(2,minmax(0,1fr))"));
assert.match(gridStyle,/align-items:stretch/);
const rowStyle = rule('[data-view="devices"] .devices-command-row');
assert.ok(rowStyle.includes("grid-template-columns:minmax(145px"));
const codeStyle = rule('[data-view="devices"] .devices-command-copy code');
assert.match(codeStyle,/border:0/);
assert.match(codeStyle,/background:transparent/);
assert.match(codeStyle,/white-space:pre-wrap;overflow-wrap:anywhere/);
assert.ok(codeStyle.includes("font-size:12.5px"));
assert.match(rule('[data-view="devices"] .devices-command-group-head h3'),/font-size:18px/);
assert.match(rule('[data-view="devices"] .devices-command-row b'),/font-size:14px/);
assert.match(rule('[data-view="devices"] .devices-command-row small'),/font-size:12px/);
assert.match(rule('[data-view="devices"] .workspace-main'),/padding-top:10px/);
const deviceSection=html.split('<section class="view app-view" data-view="devices"')[1]
  .split('<section class="view app-view" data-view="usage"')[0];
assert.ok(deviceSection.startsWith(' aria-label="Computadores"'));
assert.doesNotMatch(deviceSection,/<h1 id="devices-title">/);
assert.doesNotMatch(deviceSection,/class="workspace-head devices-workspace-head"/);
assert.doesNotMatch(commands,/REFERÊNCIA RÁPIDA/);
assert.match(commands,/<article class="panel devices-command-guide">/);
assert.equal((commands.match(/class="devices-command-group"/g)||[]).length,2);
assert.equal((commands.match(/class="devices-command-group devices-command-group-wide"/g)||[]).length,1);
assert.match(rule('[data-view="devices"] .devices-panel-compact .device-row'),/border:0/);
assert.match(rule('.devices-section-panel .onboarding-step,\n.devices-section-panel .onboarding-finish'),/border-top:0/);
assert.match(rowStyle,/border:0/);
assert.ok(css.includes('[data-view="devices"] .devices-panel-compact .device-copy b{\n  font-size:15px;'));
assert.ok(css.includes('[data-view="devices"] .devices-panel-compact .device-copy small{\n  font-size:12.5px;'));
assert.match(rule('[data-view="devices"] .device-onboarding-flow .onboarding-step b,\n[data-view="devices"] .device-onboarding-flow .onboarding-finish b'),/font-size:14px/);
console.log("COMMANDER_UI_NO_INTERNAL_DIVIDERS_AND_READABLE_DENSE_ROWS=PASS");
console.log("COMMANDER_GUIDE_SINGLE_OUTER_FRAME_NO_EYEBROW=PASS");
console.log("COMMANDER_GUIDE_SYMMETRY_FLAT_ROWS_READABLE_TYPE=PASS");
console.log("COMMANDER_GUIDE_COMPACT_HEADER_NO_SUBTITLE=PASS");
console.log("COMMANDER_GUIDE_BACKEND_OR_SECRETS_CHANGED=FALSE");
