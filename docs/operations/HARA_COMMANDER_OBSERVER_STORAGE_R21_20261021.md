# H.A.R.A. Commander R21 — Observer e Storage instalados, release público recuperado

**21/10/2026, ~18h03–18h11 UTC.** Verificação independente pelo próprio HARA Commander, usando contas já inscritas e SSH somente leitura via Services. Nenhum Agent, configuração, pareamento, Worker hospedado ou outra máquina foi alterado nesta revisão.

## Instalações reais recém-observadas — PASS

**Observer:** o proprietário demonstrou instalação pelo download público Linux, `HARA_COMMANDER_AGENT_INTEGRITY=PASS`, enrollment com ID próprio, startup attestation, autostart e `hara-commander start`. O terminal local confirmou `AGENT_ONLINE` e `PRODUCT_LEASE_REFRESH=UNMETERED` para `FOUNDER_INTERNAL`.

Por HARA Commander externo: `observer` **ONLINE**, `ping=PASS`, arquitetura **aarch64/Tegra**, Python 3.10.12, Agent **0.3.43**, `OUTBOUND_RELAY`, `ASK_EVERY_ACTION`, **31 ferramentas** e `read_file('/etc/os-release')=PASS`. O registro do dispositivo coincide com o ID apresentado pelo usuário.

**Storage:** também passou a constar **ONLINE** com cadastro próprio, Agent **0.3.43**, Fedora43/x86_64, Python3.14.4, 31 ferramentas, `OUTBOUND_RELAY`, `ASK_EVERY_ACTION`, `ping=PASS` e `read_file('/etc/os-release')=PASS`. Não alegar que foi esta revisão que instalou Storage; apenas o estado observado.

Pelo Services→SSH de ambos hosts: `hara-commander-agent.service` **active/enabled**, `device.env` permissionado **0600**, CLI presente. O binário instalado de ambos tem **SHA-256 `3e0db700dd568a85e23212a5400f1d256546fef77b7f59f574ceed29e04c15b7`**, idêntico ao Linux Agent servido no site. A sessão `hara-commander start` mantém a autorização local aberta somente enquanto o operador mantiver o terminal; seu fechamento não significa automaticamente desinstalação.

## Distribuição pública: antiga falha resolvida, mas ainda há proveniência divergente

O `verify_live_release_integrity.py --live` retornou **PASS** em 21/10 às ~18h06 UTC: manifesto de Agent **0.3.43**, assinatura v2, quatro hashes corretos e zero erros. GETs independentes do Observer e Storage às 18h08 UTC retornaram os **mesmos seis arquivos**, status HTTP200, CDN HIT:
- Manifest SHA **`53c0cbc2b074b9b85b81454c2bce286a8af2fa981e79f3c9b1719c5697880229`**.
- Signature SHA **`8ca0fdd9dc27cd9bf1136ff435893ed4cdb68f0b6a71e00ea1aaa074f24e7d0c`**, kid `commander-release-v2`.
- Linux Agent SHA **`3e0db700dd568a85e23212a5400f1d256546fef77b7f59f574ceed29e04c15b7`**.
- Linux installer SHA **`699cfcccbfd345184329870632e6b9492f359bac68ba19df0c9b1c2a0cdc4463`**.
- Windows Agent SHA **`d507a6f91a635b025ef4f06cbd758a03c7da6f3410aadec9a3d76c28f904c6fb`**.
- Windows installer SHA **`d0f6d7e3a79a87e439a6275ebf60b2918ad5ccdbc28666ce18288644f3d595b9`**.

**ATENÇÃO:** esse release público válido NÃO é byte a byte o v5 assinado na revisão R19. O manifesto R19 era SHA `2ec2b3cc...`, assinatura `6286b3ce...`; entre seus quatro assets, somente o Agent Windows tem hash idêntico ao site atual. **3/4 diferem**, embora o version string seja `0.3.43`. Isso pode representar um build/composição alternativa assinada, não prova comprometimento. O release atualmente servido deve ganhar identidade por `channel/build SHA/signature SHA`, não apenas semver. Não sobrescrever arquivos para tentar igualar sem revisão de proveniência e rollback.

## Paridade e desempenho ainda P1

Os sete Linux Founder anteriormente inscritos usam **0.3.54/Event V2** com 31 ferramentas e dois hashes de loop; Observer/Storage novos usam **0.3.43/OUTBOUND_RELAY** com 31 ferramentas. A VM Windows está offline na 0.3.53 e a fonte 0.3.55 é candidata não assinada. **10 registros existem, mas os Agents não são um único build/versão**.

Telemetria nas últimas chamadas dos dois servidores novos mostrou espera `queue_ms` frequentemente de segundos (amostras chegando a ~18,6 s em chamada do Observer); `execution_ms` tipicamente ~0,6 s. Isso não é medição causal nem SLO e nem prova falha de instalação, mas deve motivar microbenchmarks em QA por transporte e versão antes de oferecer garantias de latência a clientes.

## Próximo objetivo para Codex

1. Registrar **R21 ONBOARDING PASS** em ambos hosts e corrigir os estados obsoletos R11/R20: site atual `0.3.43/v2` foi validado, não segue em HOLD por SHA pública. Ainda existe **HOLD de igualdade com o pacote R19 / última versão** e de release train comum Linux/Windows.
2. Documentar a identidade **exata** do release efetivamente publicado (manifest sha, signature sha, build/channel) e compará-la à fonte assinada R19; explicar divergência 3/4 sem reupload cego.
3. Executar testes de lifecycle/rollback e latência **separadamente**, respeitando `ASK_EVERY_ACTION` e sessão local do usuário. Não desabilitar aprovações para agilizar.
4. Escolher release train >= fonte Windows 0.3.55, entregar pacote Linux equivalente com contrato de capabilities explícito, assinar e testar em canários antes de atualizar Founder. Evitar downgrade 0.3.54 para 0.3.43.

**Esta revisão NÃO fez atualização, reboot, deploy, alterações de credenciais ou instalação.** Código Codex rastreado intocado.
