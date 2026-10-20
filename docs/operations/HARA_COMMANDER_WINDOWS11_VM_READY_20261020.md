# HARA Commander — VM Windows 11 iniciada para homologação (20/10/2026)

Escopo: continuidade da frente Codex HARA Commander; somente HARA Commander MCP executou os comandos no host Núcleo A. Autorização do proprietário nesta conversa para ligar a VM de teste e apoiar os testes do produto. A VM **não integra a frota Linux permanente** nem autoriza alterações em Agents produtivos.

## Estado verificado

- **Domínio libvirt:** `commander-win11` (libvirt `qemu:///system`), **RUNNING**, iniciado nesta revisão com `virsh start commander-win11` (exit 0).
- Outra definição `hara-commander-win11` permanece SHUT OFF. Era uma definição adicional com disco QCOW2 muito pequeno e sem guest-agent; NÃO iniciar automaticamente para evitar duplicidade.
- **Recursos atribuídos:** 8 vCPU, 16 GiB RAM; rede libvirt `default`, interface `e1000e`, MAC `52:54:00:e0:e5:5a`.
- **IP interno DHCP:** `192.168.122.177/24`; libvirt `domifaddr --source lease` confirmado.
- **Hostname real do guest:** `HARA_WIN11`; QEMU Guest Agent `guest-ping` retorna `{}` (exit 0); `guest-get-osinfo` identifica Windows 11, kernel 10.0/build 26300.
- **Console gráfico:** SPICE `spice://127.0.0.1:5900` no próprio Núcleo. Iniciei `virt-viewer --connect qemu:///system commander-win11` na sessão gráfica Linux `sartorius` (:1); processo `virt-viewer` confirmado. O usuário pode abrir o console e fazer login Windows com sua própria conta.
- A VM não possui snapshot libvirt declarado no momento da inspeção. Não foi criada imagem, backup ou atualização de disco, nem mudado autostart.

## Bloqueio atual para testes MCP dentro do Windows

- Registro HARA Commander `HARA_WIN11` existente, último Agent reportado **0.3.53**, ainda **DEVICE_OFFLINE** quando testado o `ping` via HARA Commander. Isso não significa que a VM esteja desligada: está rodando e Guest Agent libvirt responde.
- Via QEMU Guest Agent executei **consultas somente leitura** de serviços/processos/tarefas do Windows. Existe a tarefa `HARA Commander Agent`, estado 3 (Ready), com gatilho **ao logon**, `principal_logon_type=3` (interativo), ação `powershell.exe` para `hara-commander-agent.ps1`; nenhum processo Agent/HARA nem processo explorer de sessão de usuário apareceu no instante. Nenhum serviço Windows HARA foi encontrado.
- Tentativa pontual de `Start-ScheduledTask -TaskName 'HARA Commander Agent'` retornou sem erro PowerShell, mas tarefa permaneceu Ready e nenhum processo iniciou; NÃO interpretar exit do PowerShell como prova do Agent ativo. **O login interativo do usuário é necessário antes de inferir execução do agente.** Não execute o Agent como SYSTEM via QGA, nem configure autologon ou use/salve credenciais de Windows para contornar consentimento.
- RDP/WinRM não responderam ao teste inicial de portas 3389/5985/5986 no guest. A rota confirmada é console SPICE local e QEMU Guest Agent para verificação restrita. Não mudar firewall/rede/credenciais sem plano e autorização.

## Plano para a frente Codex — somente Commander

1. **Receber estado da VM sem iniciar segunda cópia.** Conferir `virsh -c qemu:///system domstate commander-win11`. Preservar sessões Linux/Agents em uso e o domínio adicional desligado.
2. **Aguardar login interativo do proprietário pelo virt-viewer aberto**, ou uma sessão Windows legítima já ativa; então verificar tarefa `HARA Commander Agent` e o próprio `H.A.R.A._Commander.ping(computer='HARA_WIN11')`. Não afirmar ONLINE antes de uma resposta real do Agent. Se o proprietário abrir Commander Windows, ajudar usando as ferramentas expostas.
3. **Diagnóstico Windows primeiro:** `get_config` / dispositivo e Agent exatos, tarefa de startup, UI de aprovação/consentimento, conexão Event V2 ou relay, privilégios, tempo de espera e erros sanitizados. Não colocar tokens em logs.
4. **Teste das funções HARA no Windows:** descoberta/saúde, read/write/edit com CAS em arquivo descartável, busca/lista, processo one-shot curto e grande, Unicode, PTY/interação quando suportado, paginação/continuação, sessão/kill autorizado, entrega da resposta após reconexão, autorização por usuário. Comparar com testes Linux R3–R9; marcar diferenças, não forçar equivalência falsa.
5. **Paridade comercial e publicação:** versão Windows 0.3.53 instalada pode diferir do bundle candidato comercial 0.3.43. Nenhum update automático para candidato sem assinatura. Construir/validar em workspace isolado, executar instalação sob conta de usuário com consentimento, checkpoint/rollback e readback antes de qualquer upgrade.
6. Deixar `PROGRESS.md` com estados separados: VM ligada / SO responsivo / sessão de usuário / Agent MCP ONLINE / testes QA Windows / candidatura assinada / canário / PROD.

Sem deploy, sem migração D1, sem Stripe LIVE, sem nova VM, sem shutdown/reboot da frota. Os comandos de leitura via QEMU Guest Agent foram um caminho de inspeção da VM autorizada e não substituem o teste da política de permissões do Agent Windows.
