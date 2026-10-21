# HARA Commander — R14 | Decisão de instalação e prova Linux multi-arquitetura

20/10/2026 (BRT), revisão independente por Valky usando **somente H.A.R.A. Commander**. Esta revisão usa branch de evidências separada; não edita a branch/índice nem os arquivos em edição pelo Codex.

## Resposta operacional verificada ao proprietário

- **Services:** já possui o Agent interno **Founder 0.3.54/Event V2**, ping real **PASS**. Reinstalação comercial sobre esse Agent **não é necessária nem autorizada por esta revisão**; destruiria a comprovação do canário interno.
- **Sentinela A:** já recebeu o cutover **0.3.41 → 0.3.54/Event V2** com assinatura RSA v2 por device, rollback e readbacks; ping 0.3.54 **PASS** em 21/10 00:53 UTC. Não repetir a troca.
- **Outros Linux cadastrados:** Núcleo, Sentinela B/C/D e Ninja Blue 0.3.54/Event V2, cadastrados ONLINE. A mesma string de versão **não garante build igual**: pelo menos dois hashes de loop Event V2 foram encontrados na R12.
- **Storage:** Fedora 43 Server x86_64, Agent HARA principal **não instalado/cadastrado**.
- **Observer:** Ubuntu 22.04.5, **ARM64/aarch64 (Tegra)**, UID 1001, Agent HARA principal **não instalado/cadastrado**.
- **HARA_WIN11:** VM de homologação separada, Agent Founder **0.3.53** online. Windows 0.3.55 é candidato local não assinado e não deve substituir o instalado sem homologação/rollback.

**Resposta sobre instalar já:** Storage/Observer **não** podem ser instalados com segurança pelo bootstrap público enquanto o release servido tiver manifesto/assinatura/hashes incompatíveis. O P0 bloqueante é distribuição: instalador Linux público fixa `commander-release-v2`, assinatura pública usa `commander-release-v1`, e 4/4 assets publicados não conferem com manifesto. O gate público de seis GETs saiu 2/HOLD. Nenhuma opção de `curl -k`, desligar assinatura/hash ou copiar identidade de outro host é aceitável.

## Novo progresso R14 — executado realmente em ambas as distros, não apenas inspeção sintática

Transportei **somente 13 arquivos QA** (tar.gz SHA-256 `e874acc0ffeb2bf0614ad9a44ff26c3036926f84a16ff756c1f2d73a7ec5261e`, 160.107 bytes) via Núcleo→Services→Storage/Observer, com SSH BatchMode/host-key checking. Fonte: base de código local e cópia dos instaladores WIP, sem tokens, chave de assinatura privada ou arquivos do cliente. Os dois alvos conferiram o mesmo SHA do tar. A fixture gera **chave efêmera RSA de TESTE**, URL `127.0.0.1`, HOME/XDG temporários e mock de pareamento; não cria Agent, unidade systemd, D1, conta nem novo device em produção.

| Host real | Arquitetura e runtime | `test_linux_r11_pre_enroll.py` | `test_linux_r13_enrollment_ack.py` |
|---|---|---|---|
| **Storage** | Fedora 43, x86_64, Python 3.14.4, SELinux Enforcing | **exit 0**, 6/6 casos | **exit 0**, 6/6 casos |
| **Observer** | Ubuntu 22.04.5, aarch64, Python 3.10.12, usuário UID1001 | **exit 0**, 6/6 casos | **exit 0**, 6/6 casos |

Casos R11: controle de ordem antiga, assinatura KID errada, SHA alterado do Agent Linux, SHA alterado do Agent Windows, versão do Agent divergente e release válida alcançando mock de inscrição. Casos R13: respostas faltando token/ID, JSON inválido, ID inválido, confirmação perdida e compatibilidade com servidor legado. **São 12 casos por host, 24 casos ao todo**, executados na arquitetura real.

Os dois hosts têm `cryptography` instalada (Storage 46.0.7; Observer 3.4.8), `systemd --user`, DBus e user lingering habilitados. O Ubuntu ARM usa aarch64; versão Linux não depende de empacotamento x86 no caminho padrão `OUTBOUND_RELAY`, mas ainda precisa ser validada a instalação assinada e seu runtime completo. Fedora SELinux Enforcing precisa prova específica de startup, caminhos e AVC após release válido. **Esses resultados removem a suspeita de incompatibilidade básica Python/bash/RSA, não comprovam instalação real.**

Evidências sanitizadas:
- `docs/evidence/commander-portability-r14-20261020/storage.json`;
- `.../observer.json`;
- `.../qa-source-manifest.json`;
- checksums `SHA256SUMS`.

## Menor caminho correto para clientes e frota homogênea

**Gate 1 — concluir software local (Codex):** `eb31fc3` já corrigiu atomicidade da seleção D1 e retry autenticado de pareamento; seis regressões foram reexecutadas independentemente e passaram. Os dois instaladores R13 WIP também passaram nos targets reais. **Não reabrir correções resolvidas.** Finalizar o WIP, testes Windows relevantes e congelar uma fonte imutável com hash.

**Gate 2 — assinatura oficial, não mais diagnóstico de distro:** o Services possui em custódia arquivo da chave privada de assinatura v2 com permissões 0600 (verificado somente existência/permissões, **sem abrir/ler/usar a chave**). O bundle comercial `commercial-0.3.43-v5-terminal-drain` ainda não existe assinado; `stage_signed_commercial_assets.py --check` retorna `SIGNED_STAGE_CURRENT_RELEASE_AWAITING_OFFICIAL_SIGNATURE`. Solicitar aprovação específica para executar o processo formal de assinatura e publicação com a chave sob custódia autorizada; verificar assinatura v2 e todos os hashes no estágio exato, preservar rollback funcional e impedir misturas de CDN.

**Gate 3 — publicação e instalação E2E por host:** após promoção aprovada, `verify_live_release_integrity.py --live` precisa retornar PASS sobre os arquivos REALMENTE servidos, com KID/pins dos dois instaladores, assinatura e quatro hashes/versões. Executar readback por Services/Storage/Observer e só então instalar Storage e Observer com **pareamentos/credenciais próprios**, verificando PID, unit enabled/active, restart, ping via HARA Commander, arquivos/processos de QA, isolamento de tenant e rollback. Usar o Services internal como controle, sem reinstalá-lo.

**Homogeneidade de contrato ≠ mesmo número:** Founder interno Linux 0.3.54 Event V2 e comercial público 0.3.43 relay são **canais diferentes**. Não instalar `0.3.43` nos Hosts Founder só para padronizar string; exigir manifesto com `version + build SHA + channel + capabilities` por device e uma matriz de compatibilidade Windows/ARM/x86. Produto para clientes só pode ser chamado de homologado após instalação limpa E2E e assinatura/publição coerentes.

**Estados verificados:** instalação de QA via mock Fedora/Ubuntu = PASS; pacote público=HOLD; serviços Founder existentes=ONLINE; assinatura comercial atual=ausente; instalação comercial limpa PROD=**não executada**; nenhum restart/instalação/enrollment remoto neste teste. O Codex é o único escritor da implementação.
