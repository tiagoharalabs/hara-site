# H.A.R.A. Commander — 0.3.54 frota concluída / instalador público e revogação pendentes
<!-- HARA_COMMANDER_RELEASE_MANUAL_START_REVOKE_20261021_R1 -->

## Recibos e estado por 21/10/2026 23:53 UTC

- NOVE nós Linux com **Agent ativo 0.3.54**, `ping` e `device.info` pelo **produto comercial `profile=simple` PASS 9/9**: services, nucleo-a, sentinela-a, sentinela-b, sentinela-c, sentinela-d, ninja-blue, storage, observer.
- Sete nós originais mantiveram Event V2 0.3.54 (unit `hara-commander-agent-v2.service` ativa/habilitada; unit legada inativa/desabilitada; `linger=yes`).
- Storage (Fedora 43 x86_64) e Observer (Ubuntu Tegra aarch64) migraram da 0.3.43 para **0.3.54 OUTBOUND_RELAY PERSISTENT_TRUSTED**. Unit `hara-commander-agent.service` ativa/habilitada; `linger=yes`; V2 inativa; revogação/pareamento preservados. Comprovantes de ping após corte Storage `295cee06f0ce3c06177054136d8c823bef73d05d6664643da0c4efd2ca37b104`, Observer `44d57daba6d4953b31e032ec0189860700ed02b141c3f21fb1fc3633f49c7893`.
- Manifests RS256 device-bound para Storage e Observer assinados pela autoridade local existente, **private signing key não exportada**, verificados com 7/7 arquivos por host; autoteste real de ambas arquiteturas PASS.
- Backups/rollback individuais em `~/.local/share/hara-commander/preimages/fleet054-relay-20261021-r2/`, executáveis `~/.local/share/hara/codex-inbox/HARA_COMMANDER_054_ROLLOUT_20261021_R1/activate_054_relay.sh --rollback` sob `sartorius`, sem sudo.
- WARNING: Event V2 no Worker está restrito a devices canários; Storage devolveu HTTP **403** antes de trocar para Relay. Source local mapeia `DEVICE_EVENT_V2_CANARY_DENIED` a 403, mas não houve verificação da resposta JSON autenticada. Não liberar a rota experimental globalmente. O Relay é modo suportado, funcional, mesma versão 0.3.54.

## Contrato final solicitado pelo proprietário

**Frota própria**: `PERSISTENT_TRUSTED`, reconexão sem prompting por comando, systemd user `enabled/active`, `linger=yes`, preservar identidade enquanto não revogada.

**Cliente comum**: recebe código de pareamento de uso único no site; após usá-lo o token DO DISPOSITIVO é durável, não requer reemissão a cada reconexão, e só deixa de funcionar em revogação administrativa. O Agent é instalado com `PERSISTENT_TRUSTED` mas **sem abrir a conexão automaticamente**: unit instalada `disabled/inactive`, sem autostart após boot por padrão. O cliente ativa quando quiser com:
- Linux: `hara-commander start`; parar: `hara-commander stop`; status: `hara-commander status`.
- Windows: `$agent=Join-Path $env:LOCALAPPDATA 'HARA Commander\hara-commander-agent.ps1'; & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $agent start`. O modo padrão do Scheduled Task é on-demand, sem trigger de login; após instalar não iniciá-lo sozinho. Parar: mesmo script com `stop`. **Windows .55 produção instalado não foi atualizado nesta frente.**
- Enquanto ativo, o serviço reconecta e Trusted não pede consentimento em cada chamada (sem dar sudo arbitrário à IA). Se o cliente habilitar autostart em sua própria instalação, isso será decisão dele.
- O uso de `PERSISTENT_TRUSTED` deve ficar visível no site como decisão de acesso duradouro, com revogação clara.

## Publicador web — fase restante

Candidata isolada disponível em `web_candidate/`:
- `linux.sh`: instalador composto (base 13 cenários de first-install e 11 de update/rollback previamente testados) com URLs do manifesto **Linux específico**, `0.3.54` explícita, `PERSISTENT_TRUSTED` padrão, `AUTOSTART=OFF`, sem startup depois de instalar, anti-downgrade antes do backup e novamente após validar manifesto assinado.
- `linux.py`: Agent genérico público 0.3.54, SHA256 `9f27d636fa8d0b2f012bdee08dfa5996eb15d896a0da9a8dd0ba1c8b0394c58c`, derivado do arquivo já coberto por manifesto device-bound.
- `linux-agent-manifest.json`: manifesto coerente para Linux versão 0.3.54 com SHA256 `0a11a996313dae0b58cbf1b04de8d90d8e9dc2ceb8eb90fd04f1be1fde43564f`; **ainda SEM ASSINATURA**. O manifesto Windows 0.3.43 da web atual é separado e não deve ser alterado sem release Windows assinada.
- Teste `test_public_linux_054_policy.py`: **9/9 PASS**, sem login/enroll/PROD: Bash -n; source agent --version/--self-test; piso semver negativo (.55 → .54 rejeitado), manual start e Trusted; URL do Linux separada. Smoke no Storage Fedora 43 e Observer ARM64: Bash -n + Agent --version/--self-test PASS em ambos.
- **NÃO PUBLICAR** candidato até RS256 nativa, testes E2E de instalação limpa/upgrade com token de cliente, rollback, aprovação e reconexão; DEV e readback exato da versão/assinatura/assets. Bloqueio da execução deste chat: ferramenta de criação do signer/publicador foi negada por política de segurança; não contornar com outro caminho ou usar sudo para obter segredo. Code owner deve utilizar a autoridade de release nativa e seu fluxo governado.
- Atual Worker/portal PROD deve preservar seus 29 bindings e 100% da versão vigente durante homologação; `hara-site/main` NÃO é idêntico ao site implantado. O live `app.js` SHA `badbac26a0128dbfa05809f65cb2ba1fe1ac671104b4171d6defaf93710ee27e` foi salvo em `web_candidate/app.js`. A UI original no Git local difere. Necessário reconciliar antes de qualquer deploy.

## P0 segurança/UX: botão Revogar acesso

Análise read-only do **JavaScript PROD**: ao primeiro clique em `Revogar acesso` o botão muda para `Confirmar revogação` com timeout de 6 segundos, exigindo segundo clique na mesma instância DOM. Erro HTTP da chamada `POST /api/portal/devices/revoke` recebe apenas toast genérico. Ao atualizar/reconstruir a linha de dispositivo, a confirmação pode ser perdida; o usuário relata botão inoperante. A implementação de correção direta nesta sessão foi recusada por configuração de segurança das ferramentas, por isso **NÃO houve alteração da UI PROD**.

A rota backend no source atual usa `requirePortalMutationOrigin`, sessão tenant, `revokePortalDevice` e D1 batch para `state=REVOKED`, `revoked_at_utc`, remoção de seleção e cancelamento de calls pendentes. **Não se comprovou transação real de revogação de dispositivo nem atualização da versão Worker implantada.** Isso precisa de canário sintético exclusivo, sem revogar dispositivos do usuário.

Correção requerida owner #310/#189: confirmação inequívoca e estável mesmo com rerender; mostrar código de falha seguro; D1 readback de estado REVOKED; impedir uso do antigo bearer, WS, novo enqueue, polling ou comando com token revogado; cancelar pendências; exigir novo pareamento somente após revogação. Testar tenant não-owner, origin CSRF, retry e revogação de socket aberto. Não esconder erro via toast genérico.

## Próximas entregas Codex

1. **Owner hara-site#310 (release)**: conciliar sources/PR QA, assinar canal Linux 0.3.54 separado, validar ARM64/x86 e update/rollback, autenticação, publicar via DEV→canário→PROD preservando Worker e 29/29 bindings; terminar UX start manual no portal.
2. **Owner hara-site#189 (segurança)**: corrigir/aceitar revogação E2E e confirmação UX sem sacrificar controle CSRF/multitenant.
3. **Owner hara-site#163 (Event V2)**: corrigir bug TTL / reinício de LIVENESS da PR #320; não reativar indiscriminadamente Event V2 fora da allowlist; Relay permanece operacional.
4. **Owner hara-site#240 (Windows)**: compatibilizar instalação manual .55 e atualização assinada Windows sem downgrade.
5. **Torre #1953**: manter worktrees Codex intactos, sem `git add -A`, sem deploy bruto, registrar cada recibo final.

STATUS: `LINUX_FLEET_9_OF_9_PRODUCT_PING_PASS` / `LINUX_PUBLIC_054_INSTALLER_SOURCE_QA_PASS` / `LINUX_PUBLIC_054_RS256_SIGNATURE_PENDING` / `WEB_DEPLOY_NOT_PERFORMED` / `REVOCATION_E2E_UNPROVEN`.
