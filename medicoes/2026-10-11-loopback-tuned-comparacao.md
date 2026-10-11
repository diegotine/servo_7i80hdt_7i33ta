# Comparação após instalar TuneD — 11/10/2026

Anterior: loopback-20261011-174207-520.json, referência 0.2.4 Cython.
Novo: loopback-20261011-180048-574.json, 100 ciclos analógicos 0/+4 V.

**Identificação mista:** o novo registro informa interface 0.2.4, mas o runtime
já contém `_rtcore`, `native_timing=true` e `native_statistics=true`, que são
mudanças 0.2.5. A interface permaneceu aberta, mas o backend foi reiniciado após
recompilar a mesma pasta. Não atribuir toda diferença somente ao TuneD.
TuneD estava ativo com perfil latency-performance ao conferir o sistema.
O JSON não registra o perfil nem o clock durante a aquisição.

| Métrica | Anterior | Novo | Variação |
|---|---:|---:|---:|
| Média ON (ms) | 1.966883 | 1.958742 | -0.41% |
| Máximo ON (ms) | 2.037789 | 2.110464 | +3.57% |
| Desvio ON (µs) | 26.237690 | 35.626435 | +35.78% |
| Média OFF (ms) | 1.964556 | 1.947679 | -0.86% |
| Máximo OFF (ms) | 2.147232 | 2.114807 | -1.51% |
| Desvio OFF (µs) | 29.297575 | 35.660473 | +21.72% |
| Desvio do ciclo (µs) | 4.613435 | 3.744273 | -18.84% |
| Máximo do ciclo (µs) | 2085.501000 | 2037.140000 | -2.32% |
| Máximo atraso ao despertar (µs) | 95.211000 | 27.265000 | -71.36% |
| Trabalho médio leitura/cálculo/escrita (µs) | 799.402009 | 698.402179 | -12.63% |

Máximos ON e OFF separados por 4,343 µs no novo registro, contra 109,443 µs
no anterior. Isso confirma a observação de máximos próximos, mas não implica
menor dispersão ON/OFF: ambas aumentaram. O desvio do intervalo entre ciclos
caiu 18,84%. Zero work_overruns e zero skipped_slots nos dois ensaios.
As estatísticas de intervalo abrangem toda a sessão, não apenas os 100 pulsos;
contagens diferentes (11041 e 9306) limitam a comparação dos extremos.

Boot preparado com `intel_pstate=active` nos kernels instalados e nos defaults
para instalações futuras. Backup root: /var/backups/t3d-pstate-20261011T180312Z.
O boot atual não muda até reiniciar. A ativação real ainda precisa ser conferida
após reiniciar; HWP=0 e recusa de CPU híbrida foram observados no boot anterior.
