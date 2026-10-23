# Hara Commander — instrução de retomada R12 (23/10/2026)

**LEIA PRIMEIRO:** `docs/handoffs/HARA_COMMANDER_CURRENT_KIT_R12_20261023.md`. É a referência documental canônica desta rodada. Não trabalhar só a partir de excertos desta conversa.

## Estados inequívocos

**UI PROD vigente:** Cloudflare `hara-commander` **R13 `71ad29df-438b-4239-a4a3-9bf94d7f583c` 100%**, rollback R12 `b5f3b28f-c1ae-41b5-83c1-d3e5698b3825`. Login dourado e Configurações sem divisórias da R11 preservados. R13 fonte Services/Storage `b3ad8940a4023684a97453c22d0496d46c756687`, closeout `f870560fa14053a7ae6628f3fd713f57e9b55c02`. A fonte ainda não foi publicada como código na branch Web do GitHub, só os handoffs.

**Agent Núcleo A — causa corrigida e readback 23/10:** antes da promoção, a CLI `~/.local/bin/hara-commander` era `0.3.54`, mas o serviço systemd executava o binário antigo `~/.local/share/hara-commander/hara-commander-agent` `0.3.41` (não era apenas metadado atrasado). Binário do serviço promovido para `0.3.54`, SHA256 `ea42a392a6d350bb6e7e522cca5498ee823d2c41587855d0d3d1ecc41a954da2`; reinício do serviço às 13h49min21s BRT; `active/running`, `PERSISTENT_TRUSTED`, ping e versão `0.3.54` confirmados, matrícula preservada; backup `~/.local/share/hara-commander/rollback/hara-commander-agent.0.3.41.e1f44e4695266717.bak`. Não reiniciar/atualizar novamente sem motivo.

**Revogação/Histórico R13 ENTREGUE EM PROD:** botão `Revogar acesso` com confirmação persistente/cancelar e validação da API (sem revogação real do proprietário nesta entrega). `Dispositivos → Histórico → Limpar histórico` faz POST autenticado e **DELETE real das entradas do Histórico no D1**, não apenas ocultação local; opção Mostrar ocultos/Restaurar todos removida. `0036_portal_device_history_clear.sql` aplicada em PROD, readback 8 revogados/8 histórico/0 limpezas executadas; auditoria, recibos e matrículas revogadas preservados. Testes 36 JS + 7 SQLite PASS; Worker/GET externa e API não autenticada verificados. Histórico R10 ocultar abandonado, R12 publicada antes da R13. `HARA_WIN11` antiga ainda não foi revogada por este rollout.

**Resiliência P0 — Storage #322:** falha independente da atualização do Núcleo. O Agent Storage `0.3.54` ficou vivo mas sem comunicação por ~12h35; `WatchdogUSec=0` e heartbeat/chamada no mesmo loop. Chamada `hara.files.list` terminou somente em `RECEIVED`, sem prova de execução; instrução interna causadora não determinada. Protótipo supervisor com 19 testes offline PASS está isolado no Services, **não commitado, não publicado nem ativado**. A correção definitiva exige isolamento de chamadas, watchdog, alertas independentes, recovery E2E e parity Windows antes da release comercial.

**Instaladores P0:** manifesto público assinado antigo `0.3.41` não corresponde a 4/4 files atuais; Linux Agent `0.3.43`, Windows Agent `0.3.52`. Release comercial `0.3.56` é candidata **não assinada** com testes offline PASS; Windows ExecutionPolicy bloqueia .ps1 por arquivo. Owner Codex #310 e QA Windows #240. Sem signer/admissão/E2E/readback, `PUBLIC_INSTALLERS=HOLD`.

**VMs da outra frente:** `hara-review-win11` + `hara-review-linux` Ubuntu Server 24.04.5 na Sentinela B, autostart e firewall; não refazer as instalações. Instalar/parear os Agents REVIEW continua gate separado.

**OpenAI Plugin Directory:** plugin draft v0.2.0 carregado, domínio/OAuth/MCP 33 tools OK, Review Information incompleta e NÃO SUBMETIDO. Conta `openai-reviewer@haralabs.com.br` / tenant `HARA Review`. Senha privada só na OpenAI. Restam login sem MFA, 5 positivos + 3 negativos reais, vídeo demo e Submit for review.

## Ordem para executar

1. Consultar Cloudflare/GET e Git para confirmar R11 e mudanças posteriores. Não confundir versões Cloudflare, Git e OpenAI.
2. Codex fechar #310: .56 comercial autêntica, distribuir Windows nativo SEM Bypass, assinaturas e hashes completos, QA real Linux/Windows, upload 0%, promotion 100%, readback e rollback.
3. Não repetir a UI R10/R12: **R13 já está publicada a 100% e verificada**; validar uso real só com o operador autenticado, sem clicar em Limpar histórico ou Revogar acesso nas máquinas reais sem pedido específico. Preservar D1 0036, readback e rollback R12.
4. Ao receber VMs pareadas da outra frente, rodar testes reais do tenant HARA Review; preencher revisão e gravar vídeo.
5. Publicar evidência separada no Git **Services, Storage e GitHub Web** com SHAs; preservar staging e branches do Codex.

**Política permanente:** Hara Commander produto MCP comercial; não confundir com Desktop/Baseline ou MCP interno. Comunicação entre hosts só rede; USB Link aposentado. Nunca publicar senhas, tokens ou credenciais de revisão em documentação.