# Performance sem Turbo Boost

Alterações de sistema autorizadas pelo operador em 11/10/2026, sem mudança no
código do aplicativo e sem acesso à placa.

- BIOS Dell TurboMode: Enabled → Disabled, confirmado por leitura após escrita.
- BIOS pending_reboot: 1; alteração de firmware aguarda próximo reboot.
- Perfil TuneD anterior: mesa, herdando desktop. Preservado.
- Novo perfil ativo: mesa-performance-sem-turbo, baseado em latency-performance;
  governor, EPP e EPB performance, min_perf_pct=100 e boost=0.
- Linux intel_pstate.no_turbo=1, governador/EPP performance confirmados.
- CPU 5 limites mínimo/máximo: 2500000/2500000 kHz; frequência base 2500000 kHz.
- intel_idle.max_cstate=1 mantido. Contadores de limitação térmica zero.

| Amostra (1 s) | Busy % | Bzy_MHz | CPU °C | Pacote °C |
|---|---:|---:|---:|---:|
| 1 | 11,08 | 1489 | 49 | 50 |
| 2 | 11,52 | 1484 | 48 | 50 |
| 3 | 12,47 | 1585 | 48 | 51 |
| 4 | 11,28 | 1466 | 48 | 50 |
| 5 | 10,57 | 1379 | 49 | 50 |

Fonte: turbostat executado como root, CPU 5. Leitura instantânea de
scaling_cur_freq após ativação: 2500054 kHz; leitura posterior: 2297798 kHz.
Os limites pedidos ao kernel estão em 2,5 GHz, mas a frequência efetiva medida
em baixa carga ainda varia. Não se confirmou estabilidade física nem redução
de jitter com este perfil. Falta medir a malha real e conferir após reboot.

O alvo de 4200 MHz ainda presente no auxiliar da interface não é atingível sem
turbo; ao reabrir, pode gerar aviso de limites não confirmados pelo kernel.

Para desfazer: reativar TurboMode na BIOS (requer reboot) e selecionar o perfil
TuneD anterior `mesa`. O perfil anterior e seus arquivos não foram sobrescritos.
