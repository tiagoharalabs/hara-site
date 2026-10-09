# H.A.R.A. Commander — arquitetura comercial Cloud-first e submissão pública

Data: 2026-10-09 | Branch canônica: `local/commander-product-current`

## Decisão de produto

O fluxo principal de distribuição é **o mesmo modelo comercial do Remote Desktop Commander**:

```
ChatGPT (plugin H.A.R.A. Commander, capivara dourada)
  -> MCP HTTPS público `commander.haralabs.com.br/api/mcp?profile=simple`
  -> autenticação HARA Identity OAuth + autorização por tenant e device + limites
  -> transporte comercial do H.A.R.A. Commander via Cloudflare
  -> Agent na máquina do cliente -> execução e confirmação local
  -> resultado pelo mesmo Gateway ao ChatGPT
```

**Todas as chamadas do plugin público passam pelo Gateway da H.A.R.A.** Os argumentos e os resultados transitam por esse Gateway. O sistema do cliente executa as ações; o HARA Services administrativo *não* é o proxy do MCP comercial. O cliente não precisa criar uma chave OpenAI Platform nem configurar um túnel da OpenAI. A integração ao ChatGPT exige autenticação OAuth normal e, enquanto o plugin não for publicado, uma conexão MCP personalizada por URL.

O Commander Direct (Secure MCP Tunnel da OpenAI, privado por workspace) permanece como **opção avançada Linux**, sem ser um pré-requisito do lançamento comercial.

## Privacidade — declaração precisa e verificável

- No modo Cloud, dados dos comandos **transitam** pela Cloudflare e não devem ser descritos como exclusivamente locais ou como inacessíveis à H.A.R.A.
- O fallback de fila durável atualmente **persiste `payload_json` e `result_json` em D1**, para executar/retornar a solicitação mesmo diante de indisponibilidade temporária. O TTL nominal de chamada é **50 segundos**. A rotina de manutenção é acionada em cron (`17 * * * *`); por isso, a efetiva redação pode ocorrer mais tarde, sem garantia de apagar exatamente aos 50 s. Após a redação, permanecem marcadores SHA-256, metadados e eventuais logs de infraestrutura conforme a política aplicável.
- Há um canal transitório Event V2 quando as condições de conexão permitem, que não precisa gravar os conteúdos de tool calls em D1. Isso **não** autoriza prometer zero persistência em todos os caminhos.
- O sistema mantém metadados operacionais e contagem de transações. A política comercial não deve alegar que a H.A.R.A. não processa ou não vê conteúdo transmitido pelo Gateway.
- Não enviar comandos/arquivos para treinamento de IA H.A.R.A.; analítica de aprendizado é limitada a sinais derivados e sem conteúdo, conforme o contrato existente.
- O Agent mantém autorizações locais; uma solicitação Cloud não ignora uma recusa ou política de segurança do usuário.

## Mudanças realizadas na fonte candidata

- `apps/commander/public/install/linux.sh`: **OUTBOUND_RELAY** padrão de novos clientes; DIRECT requer seleção explícita. Bloqueio de autostart Direct em transporte Cloud; `update` baixa `tunnel-client` apenas quando necessário; instrução pós-instalação informa URL comercial + OAuth.
- `apps/commander/public/index.html` + `app.js`: onboarding Cloud-first, modo Direct avançado e revelação explícita do trânsito de conteúdo pelo Gateway. Seleção de transporte Linux no comando gerado; Direct não oferecido no Windows.
- `apps/commander/plugin-submission/plugin.json`, `mcp.json` e `assets/{logo,icon}.png`: **rascunho de submissão**, com identidade H.A.R.A. Labs e capivara, endpoint comercial único, cinco casos positivos e três negativos de revisão. Nenhuma chave/reviewer password no repositório.
- `apps/commander/scripts/validate_cloud_launch_contract.py`: testa separação Cloud/Direct, identidade, endpoint, pacote, logo e o aviso de retenção transitória de conteúdo.
- Preservados `validate_prod_static.py`, `validate_linux_tunnel_start_modes.py`, `validate_local_tunnel_control_plane.py`, `validate_customer_privacy_noc_contract.py` e testes Node MCP.

## Publicação segura

A versão 0.3.41 do Agent/instaladores continua a única **release estável assinada** em produção. A fonte 0.3.43 é candidata e ainda não pode ser promovida para distribuição sem resolver a divergência legítima entre a chave privada de assinatura e a JWK pública fixada. **Não** desabilitar assinatura nem trocar âncora de confiança sem autorização formal.

As mudanças da interface Cloud podem ser publicadas separadamente mediante staging com os quatro binários e manifesto/sig/SHA256SUMS **exatamente iguais aos assinados 0.3.41**, sem contaminar o release. Só anunciar deploy quando houver readback real.

## Pendências externas / antes do diretório

1. Homologar a **conexão do ChatGPT ao MCP comercial** (não o Baseline Services) com conta de cliente de teste via OAuth; ler e executar uma operação autorizada na máquina de demonstração, com recibo, isolamento e negados.
2. Verificar oficialmente a identidade da H.A.R.A. Labs na OpenAI, garantir permissões de gerenciamento e completar o desafio de domínio exigido na interface de submissão.
3. Registrar vídeo demonstrativo, criar uma conta de revisor com dados de demonstração e comprovar os 5 casos positivos e 3 negativos; os casos do pacote são **roteiros propostos**, não provas executadas.
4. Completar verificação de segurança e submissão do pacote na OpenAI. A aprovação/publicação é externa; o ícone da capivara aparecerá como identificação do plugin somente após instalação/conexão aprovada.
5. Ativar Stripe com credenciais e validação de checkout quando for comercializar planos pagos. Não bloquear testes beta gratuitos por isso.

Documentação atual: https://developers.openai.com/plugins/deploy/submission

## Evidência desta rodada

- `validate_cloud_launch_contract.py`: PASS.
- `validate_prod_static.py`: PASS.
- `validate_linux_tunnel_start_modes.py`: PASS.
- `validate_local_tunnel_control_plane.py`: PASS.
- `validate_customer_privacy_noc_contract.py`: PASS.
- `test_customer_mcp_simple_profile.mjs` e `test_customer_mcp_edge.mjs`: PASS.
- `node --check apps/commander/public/app.js` e `bash -n apps/commander/public/install/linux.sh`: PASS.
- A release signature de 0.3.43 **continua pendente**; não confundir a validade do código candidato com a publicação de um Agent assinado.
