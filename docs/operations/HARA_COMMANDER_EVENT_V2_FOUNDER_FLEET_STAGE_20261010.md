# H.A.R.A. Commander — preparação histórica do rollout Event V2 na frota Founder

> **ETAPA CONCLUÍDA:** este registro descreve a preparação antes das ativações. Para o resultado pós-deploy ver `docs/handoffs/HARA_COMMANDER_FLEET_EVENT_V2_HANDOFF_20261010.md`: 7/7 Linux Founder em Event V2 0.3.44, Worker atualizado e provas comerciais PASS.
**10/10/2026 — checkpoint de preparação, NÃO uma declaração de rollout completo**

## Autoridades e baseline
- Branch única: `local/commander-product-current`, base verificada `47d2280439d099f38ef092147d3e6fbc4ed8e4f4` no GitHub.
- O plugin comercial `H_A_R_A__Commander` respondeu no Núcleo A: `operational_authority=HARA_COMMANDER`, `execution_authority=HARA_COMMANDER_AGENT`, Agent `0.3.44`, `EVENT_V2`. O resultado de `list_devices` e `get_activity` agregados pode rotular `HARA_SERVICES`; não substitui o E2E por dispositivo.
- Núcleo A permanece como canário ativo, com serviço v2 persistente e watchdog. A v1 assinada 0.3.41 fica para rollback.
- Os demais agentes Linux comerciais continuavam em `0.3.41 / OUTBOUND_RELAY` na inspeção inicial.
- Históricos `HARA_WIN11` revogados/offline não são alvos válidos de atualização remota.

## Trabalho efetivamente preparado
- Novo `event_v2_founder_fleet_release.py` produz manifesto RS256 e launcher 0.3.44 vinculados ao ID do dispositivo; aproveita os seis artefatos já validados do pacote Founder. A chave RSA privada v2 permanece **somente no Services**.
- Pacotes assinados separados foram preparados no Services em `/tmp_hara/commander-event-v2-0.3.44-fleet-<hostname>-signed-r3` para `sentinela-a/b/c/d`, `ninja-blue` e `services`. O diretório é temporário, NÃO um repositório permanente de releases.
- A Sentinela C recebeu seu bundle em `~/.local/share/hara-commander/releases/0.3.44-fleet-event-v2`, com assinatura, seis hashes, versão, origem e ID conferidos. **O serviço antigo permaneceu ativo; não houve corte.**
- `worker.js` agora entende `DEVICE_EVENT_V2_ADDITIONAL_DEVICE_IDS` como allowlist extra somente em PROD, limitada a oito UUIDs válidos e sem duplicatas, com recusa de curingas ou identidade fora da lista. Ausente a variável, **somente o Núcleo canário é autorizado**.
- Por privacidade, os IDs adicionais NÃO foram persistidos no `wrangler.jsonc` versionado; a variável precisa ser configurada em canal de configuração de produção autorizado e não em código público.
- O Worker de produção **NÃO foi alterado** neste checkpoint. O `wrangler deploy --dry-run` com assets públicos v1 assinados passou.

## Regressão e segurança
- PASS: `validate_event_v2_wiring.py`, `validate_event_v2_websocket_client.py`, `validate_event_v2_persistent_guard.py`, `validate_multitenant_isolation.py`, `validate_prod_fail_closed.py`, `validate_prod_contracts.py`, `validate_prod_static.py`.
- PASS: `validate_event_v2_fleet_allowlist.mjs` (Fundador e C aceitos; cliente desconhecido, lista duplicada, curinga, entrada inválida e DO não autorizado negados).
- PASS: assinaturas e hashes RSA/RS256 dos bundles de cada host; `PYTHONDONTWRITEBYTECODE=1` na geração para impedir bytecode extra não assinado.
- Pacote 0.3.44 Founder original e versão pública v1 0.3.41 não foram sobrescritos.
- A ferramenta de edição recusou uma tentativa adicional de restringir o empacotador à allowlist do Wrangler. Não usar outra rota para contornar esse bloqueio; marcar revisão adicional do escopo do assinador antes do rollout externo.
- O SSH de `sentinela-a` resolveu para `192.168.10.21`, mas foi recusado porque a chave de host ED25519 não estava confiável. **Não desativar StrictHostKeyChecking.**

## Gates para aplicação, ainda em aberto
1. Aprovar/persistir a allowlist extra pela configuração protegida do Worker; conferir tenant/device e Cloudflare readback. Não publicar IDs internos em `wrangler.jsonc`.
2. Preparar no host serviço v2 exclusivo, `ExecStartPre` com verificador, `PYTHONDONTWRITEBYTECODE=1`, `Conflicts` com v1, timer watchdog sem `PrivateTmp`; testar fallback e impedir dois Agents com o mesmo token.
3. Primeiro corte controlado na Sentinela C, prova pelo **plugin comercial** de `EVENT_V2/HARA_COMMANDER`, recibos e D1. Em falha, retornar para v1 automaticamente ou por rollback local.
4. Somente após C homologada, migrar B, D, Ninja; Services **por último** e com cuidado para não interromper o backend. Resolver confiança SSH da A antes de tocá-la.
5. Windows, Free quota/isolamento externo, cold boot, failover forçado, custo real Cloudflare, checkout Stripe e suporte a clientes externos continuam sem homologação completa.

## Comercialização — preflight PROD 10/10
- `TRIAL`: 10.000 operações governadas por mês; `STANDARD`: R$80/mês no catálogo, ilimitado. `SCALE` não ativo.
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_STANDARD` ainda pendentes.
- `BILLING_CONNECTIONS=0`, `BILLING_WEBHOOK_EVENTS=0`, `COMMANDER_BILLING_FIRST_CHECKOUT_READY=FALSE`.
- **Não prometer venda por assinatura funcionando até checkout, webhook assinado e ciclo de entitlement serem provados.**

## Governança Git
- GitHub `local/commander-product-current` e checkout da frente estavam em `47d2280` antes desta preparação.
- Storage `origin` divergente em `092f35a` e protegido: não forçar, não reescrever ref, não confundir com GitHub.
- Verificar/preservar hashes exatos ao publicar alterações; atualizar documentação CURRENT somente após mudança real de estado.
