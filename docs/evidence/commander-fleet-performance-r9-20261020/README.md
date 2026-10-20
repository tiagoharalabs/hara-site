# HARA Commander — evidências sanitizadas R9, 20/10/2026

Métricas oriundas de get_activity (24h + últimas 100), list_devices/get_config/list_sessions, leituras de /proc/meminfo + /proc/loadavg + root disk e NVIDIA-SMI em sete Agents, SSH apenas leitura de Services para Observer/Storage e 12 chamadas MCP read_file a /etc/os-release.

Os arquivos JSON não registram payloads de cliente, dados bancários, comandos de usuário nem tokens. A atividade histórica foi agregada; métricas GPU/CPU/disco são snapshots. Os 100 eventos recentes não são amostra aleatória do período de 24 horas. A janela do microteste teve exatamente 12 file reads identificadas por função/destino e data, mas a correlação é temporal. Não é benchmark comercial ou teste de carga da frota.

Observer e Storage não estão cadastrados como Agents neste escopo, foram consultados via SSH read-only a partir do Services pelo próprio HARA Commander. Falha transitória DEVICE_OFFLINE em uma cópia de arquivo de QA foi seguida por ping PASS; sem afirmar queda de computador.

O relatório correspondente é docs/operations/HARA_COMMANDER_FLEET_PERFORMANCE_R9_20261020.md. A implementação continua exclusivamente na branch Codex; nenhuma mutação de código de produto ocorreu nesta revisão.

Independent fixed-commit verification of existing caef476 device discovery is in reachability-local-test.json (exit 0; not installed).
