# H.A.R.A. Commander — expiração na listagem de chamadas

Data: 2026-10-12  
Base: `3b4f791147be54919727628e9c577963af030e3f`  
Branch: `local/commander-call-expiry-status-20261012`  
Estado: código revisado e testes offline aprovados; sem deploy em produção.

## Problema e comportamento corrigido

O Worker aceita chamadas por 50 segundos. O MCP espera até 45 segundos. A seleção
em `claimNextDeviceCall` exige `expires_at_utc > now`, enquanto a manutenção
programada materializa `EXPIRED` no minuto 17 de cada hora. A listagem anterior
lia somente o estado persistido. Por isso, uma chamada vencida podia aparecer
como `PENDING` até a manutenção seguinte, embora já não pudesse ser entregue.

A listagem agora inclui o prazo e calcula o estado efetivo com um único instante
observado após sua SELECT. Para `PENDING` ou `EXECUTING` com prazo válido menor
ou igual ao instante observado, retorna `EXPIRED`. Mantém os estados terminais,
o estado persistido e os metadados existentes. A consulta continua com uma
SELECT, os mesmos filtros de tenant/subject e nenhuma escrita em D1.

| Campo | Contrato |
|---|---|
| `state` | Estado efetivo, incluindo expiração derivada do prazo. |
| `effective_state` | Mesmo valor de `state`, tornando a projeção explícita. |
| `persisted_state` | Estado retornado pela SELECT, sem modificação. |
| `expires_at_utc` | Prazo original; `null` quando ausente. |
| `expiry_origin` | `DEADLINE_PROJECTION` quando a expiração foi derivada; caso contrário, `null`. |
| `claimed_at_utc`, `completed_at_utc`, `error_code` | Metadados persistidos preservados, sem inventar conclusão ou código de erro. |

Um prazo ausente ou inválido não produz uma expiração inventada. A mesma
projeção chega ao resultado de `hara.calls.recent`: o wrapper preserva os
registros completos da listagem.

## Expiração e resultado da execução

`DEADLINE_PROJECTION` em uma chamada persistida como `EXECUTING` significa que
o prazo da chamada venceu. **Não prova que a operação nunca executou.** O
processo pode ter iniciado ou concluído uma ação sem conseguir comunicar seu
resultado dentro do prazo. O instante de claim continua disponível.

A projeção não altera resultados, recibos ou o estado persistido. Uma chamada
pode retornar `state=EXPIRED`, `persisted_state=PENDING`,
`completed_at_utc=null` e `error_code=null`: isso mostra precisamente que o
prazo venceu e a expiração ainda não foi materializada no registro.

A listagem não concede nova autorização e não permite inferir
`automatic_retry_allowed=true`. Recuperação ou repetição de uma operação
mutante exige a reconciliação aplicável ao produto e sua aprovação por ação.
A consulta canônica `deviceCallStatus` e a manutenção programada continuam
responsáveis por materializar a expiração em D1.

## Validação

- Testes do helper real e da consulta real: **36/36 PASS**.
- Fronteira de 50 segundos antes, no instante exato e após o prazo; estados
  `PENDING`/`EXECUTING`; terminais preservados; prazos inválidos; snapshot único.
- Tenant/subject e filtros preservados; uma SELECT e nenhuma escrita.
- Objeto `EXECUTING` e recibos congelados: dados originais intactos e privados.
- Controle negativo com a função real da base: antes `PENDING` vencido; depois
  `EXPIRED` efetivo com `persisted_state=PENDING`.
- Parser Node: PASS. Gate offline: **98/98 PASS**.
- Agent Windows 0.3.48 preservado, SHA-256
  `f54e5ff8c170e09a3dc795004af426851d111c89ae78408559886e0d693bf805`.

Evidências: [commander-call-expiry-status-20261012](../evidence/commander-call-expiry-status-20261012/).

Nenhum deploy Cloudflare, escrita manual em D1, acesso à VM, modificação de
Agents/bundles ou alteração de Stripe ocorreu nesta correção. Os testes são
offline; não comprovam aprovação humana positiva pelo MCP Windows nem escala
real de clientes.
