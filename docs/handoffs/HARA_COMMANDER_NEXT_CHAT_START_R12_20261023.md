# Hara Commander — instrução de retomada R12 (23/10/2026)

**LEIA PRIMEIRO:** `docs/handoffs/HARA_COMMANDER_CURRENT_KIT_R12_20261023.md`. É a referência documental canônica desta rodada. Não trabalhar só a partir de excertos desta conversa.

## Estados inequívocos

**UI PROD entregue:** Cloudflare `hara-commander` versão R11 `dd25fde5-d8d2-4a70-af80-5f58dce8cd8d` 100%; rollback `20540b42-c5d2-4a90-98e9-01500368d7f1`. Login com destaque dourado e sem avisos redundantes, Configurações sem divisórias internas. Commit R11 `894890b` + closeout `583b60f`.

**Agent Núcleo A — causa corrigida e readback 23/10:** antes da promoção, a CLI `~/.local/bin/hara-commander` era `0.3.54`, mas o serviço systemd executava o binário antigo `~/.local/share/hara-commander/hara-commander-agent` `0.3.41` (não era apenas metadado atrasado). Binário do serviço promovido para `0.3.54`, SHA256 `ea42a392a6d350bb6e7e522cca5498ee823d2c41587855d0d3d1ecc41a954da2`; reinício do serviço às 13h49min21s BRT; `active/running`, `PERSISTENT_TRUSTED`, ping e versão `0.3.54` confirmados, matrícula preservada; backup `~/.local/share/hara-commander/rollback/hara-commander-agent.0.3.41.e1f44e4695266717.bak`. Não reiniciar/atualizar novamente sem motivo.

**Revogação/Histórico P1:** R10 testada com cinco casos simulados; R12 integrada em `04fd70cfc71fe4d423b10adbed225d633a5b0810`, com 21 verificações R12 PASS e conflito histórico `UU apps/commander/public/index.html` já resolvido (`git ls-files -u` = 0 em 23/10 às 13h50 BRT). **Ainda não publicada em PROD.** Preservar `node_modules` não rastreado; não sobrescrever trabalho de outras frentes. Matrícula legada `HARA_WIN11`, ID final `e8b48d00`, não é VM Win11 de revisão; revogação real NÃO confirmada.

**Resiliência P0 — Storage #322:** falha independente da atualização do Núcleo. O Agent Storage `0.3.54` ficou vivo mas sem comunicação por ~12h35; `WatchdogUSec=0` e heartbeat/chamada no mesmo loop. Chamada `hara.files.list` terminou somente em `RECEIVED`, sem prova de execução; instrução interna causadora não determinada. Protótipo supervisor com 19 testes offline PASS está isolado no Services, **não commitado, não publicado nem ativado**. A correção definitiva exige isolamento de chamadas, watchdog, alertas independentes, recovery E2E e parity Windows antes da release comercial.

**Instaladores P0:** manifesto público assinado antigo `0.3.41` não corresponde a 4/4 files atuais; Linux Agent `0.3.43`, Windows Agent `0.3.52`. Release comercial `0.3.56` é candidata **não assinada** com testes offline PASS; Windows ExecutionPolicy bloqueia .ps1 por arquivo. Owner Codex #310 e QA Windows #240. Sem signer/admissão/E2E/readback, `PUBLIC_INSTALLERS=HOLD`.

**VMs da outra frente:** `hara-review-win11` + `hara-review-linux` Ubuntu Server 24.04.5 na Sentinela B, autostart e firewall; não refazer as instalações. Instalar/parear os Agents REVIEW continua gate separado.

**OpenAI Plugin Directory:** plugin draft v0.2.0 carregado, domínio/OAuth/MCP 33 tools OK, Review Information incompleta e NÃO SUBMETIDO. Conta `openai-reviewer@haralabs.com.br` / tenant `HARA Review`. Senha privada só na OpenAI. Restam login sem MFA, 5 positivos + 3 negativos reais, vídeo demo e Submit for review.

## Ordem para executar

1. Consultar Cloudflare/GET e Git para confirmar R11 e mudanças posteriores. Não confundir versões Cloudflare, Git e OpenAI.
2. Codex fechar #310: .56 comercial autêntica, distribuir Windows nativo SEM Bypass, assinaturas e hashes completos, QA real Linux/Windows, upload 0%, promotion 100%, readback e rollback.
3. Integrar a UI R10 de revogação com base em R11 sem `UU`, testar e publicar separadamente.
4. Ao receber VMs pareadas da outra frente, rodar testes reais do tenant HARA Review; preencher revisão e gravar vídeo.
5. Publicar evidência separada no Git **Services, Storage e GitHub Web** com SHAs; preservar staging e branches do Codex.

**Política permanente:** Hara Commander produto MCP comercial; não confundir com Desktop/Baseline ou MCP interno. Comunicação entre hosts só rede; USB Link aposentado. Nunca publicar senhas, tokens ou credenciais de revisão em documentação.