# Ensaios adicionais antes do reboot — 11/10/2026

Registros 180456-898 e 180655-190 preservados integralmente nesta pasta.
O perfil foi alterado pelo operador. O JSON não identifica o perfil em cada
ensaio. Ambos ainda combinam interface 0.2.4 e módulos da pasta principal com
_rtcore 0.2.5, conforme runtime.native_modules. O atalho 0.2.4 agora aponta para
uma compilação separada, mas a janela/processo em execução não foi reiniciado.

| Métrica dos 100 pulsos | 18:04:56 UTC | 18:06:55 UTC |
|---|---:|---:|
| Média ON (ms) | 2.005610 | 1.960818 |
| Média OFF (ms) | 2.009968 | 1.968568 |
| Máximo ON (ms) | 2.070536 | 2.026775 |
| Máximo OFF (ms) | 2.057837 | 2.048945 |
| Desvio ON (ms) | 0.037743 | 0.034338 |
| Desvio OFF (ms) | 0.032450 | 0.032434 |

Último teste: 100 ciclos, concluído sem erro. Máximos ON/OFF menores que no
registro anterior e separados por 22,170 µs. Desvios ON/OFF 34,338/32,434 µs.

Os contadores de temporização são acumulados desde a conexão. A sessão passou
de 133468 para 192608 ciclos, e inclui alterações de perfis e compilações feitas
com o app aberto. No último registro: intervalo máximo 8,006786 ms, trabalho
máximo 6,391258 ms (escrita máxima 5,809663 ms), 2 work_overruns e 6 skipped_slots.
No registro anterior estes contadores eram zero. Não se pode localizar os eventos
nos 100 pulsos nem atribuí-los somente ao perfil com os dados disponíveis.
O P95 recente do intervalo no último registro foi 2,007507 ms.

Comparar novamente após reboot, com versão 0.2.5 identificada pelo núcleo e
sessão nova, sem recompilações durante o ensaio.
