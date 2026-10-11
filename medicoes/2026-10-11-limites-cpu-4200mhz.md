# Validação dos limites de CPU — 0.2.5

Validação real de sysfs em 11/10/2026, sem acesso à placa e sem reiniciar a
instância do operador. CPU 5, intel_pstate ativo/HWP, perfil TuneD desktop.

| Parâmetro | Antes | Durante a sessão | Após EOF / SIGTERM |
|---|---|---|---|
| scaling_min_freq (kHz) | 2501000 | 4200000 | 2501000 |
| scaling_max_freq (kHz) | 2501000 | 4200000 | 2501000 |
| scaling_governor | powersave | powersave | powersave |
| energy_performance_preference | balance_performance | balance_performance | balance_performance |
| energy_perf_bias | 6 | 6 | 6 |
| pm_qos_resume_latency_us | 0 | 0 | 0 |

Foram realizadas duas sessões separadas do auxiliar instalado, uma encerrada
por EOF e outra por SIGTERM; ambas confirmaram os limites e a restauração.
O primeiro ensaio detectou leitura prematura dos limites, antes da aplicação
assíncrona pelo kernel. Corrigido com confirmação limitada a 1 segundo por
gravação, fora da malha de controle. Os resultados da tabela são posteriores
à correção. O estado original foi restaurado antes e depois dos dois ensaios.

Compilação concluída sem novos avisos; `gui_smoke` passou. A instância já aberta
usa o código anterior: reabrir a 0.2.5 para iniciar a nova sessão automaticamente.

Esta validação confirma os limites pedidos ao kernel. Não mede a frequência
física sob carga, o jitter ou a latência de loopback. Não há alegação de ganho
de desempenho; a próxima medição física permitirá avaliar isso.

Referências primárias:

- [CPUFreq — atributos de política](https://docs.kernel.org/admin-guide/pm/cpufreq.html)
- [Implementação CPUFreq — pedidos QoS e atualização da política](https://github.com/torvalds/linux/blob/master/drivers/cpufreq/cpufreq.c)
