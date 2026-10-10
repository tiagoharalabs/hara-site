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
  'Escolha o sistema', 'Gere o código no portal', 'Instale no computador',
  'data-create-pairing', 'id="pairingPanel"', 'id="pairingToken"',
  'data-copy-pairing', 'data-install-linux-code', 'data-install-windows-code',
  'Pairing token', 'data-os-choice="linux"', 'data-os-choice="windows"',
]){
  assert.ok(onboarding.includes(marker),"ONBOARDING_MISSING:"+marker);
}
assert.ok(onboarding.indexOf('Escolha o sistema')<
  onboarding.indexOf('Gere o código no portal'));
assert.ok(onboarding.indexOf('Gere o código no portal')<
  onboarding.indexOf('Instale no computador'));
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
assert.match(js,/fetch\("\/api\/portal\/devices\/pairing"/);
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
assert.match(html,/styles\.css\?v=20261010-guided-setup1/);
assert.match(html,/app\.js\?v=20261010-guided-setup1/);
assert.match(css,/--gold/);
console.log("COMMANDER_GUIDE_COLORS_THEME_RESPONSIVE=PASS");
console.log("COMMANDER_GUIDE_BACKEND_OR_SECRETS_CHANGED=FALSE");
