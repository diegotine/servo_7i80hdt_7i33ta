# Loopback com otimizações — código renumerado para 0.2.2

O operador executou o teste com o título ainda indicando **v0.2.1** e
solicitou que a versão com otimizações fosse corrigida para **0.2.2**.
O JSON e a captura foram preservados com a identificação original.
Esta correção de numeração não altera os algoritmos medidos.

100 ciclos, Motor 1, analógico 0/+4 V (40%).

| Medida | ON | OFF |
|---|---:|---:|
| Média | 4,982 ms | 4,972 ms |
| Mínimo | 4,782 ms | 4,670 ms |
| Máximo | 5,668 ms | 5,149 ms |
| P95 | 5,103 ms | 5,105 ms |
| Desvio padrão | 0,104 ms | 0,089 ms |

O JSON confirma afinidade na CPU 5, mas **SCHED_OTHER / prioridade 0** e
**memória atual não bloqueada**. Pedidos de prioridade e bloqueio falharam
com `Operation not permitted` e `Cannot allocate memory`, respectivamente.
Portanto, não apresentar esta execução como teste com todos os ajustes ativos.

Na sessão de 8385 ciclos, intervalo médio 5,000008561 ms, mínimo 2,873805 ms,
máximo 7,123525 ms, desvio 0,112543 ms e nenhum horário pulado. Médias de
leitura 0,467288 ms, cálculo/comandos 0,010288 ms e escrita 0,285636 ms.
Essas estatísticas cobrem a sessão até o resultado, não apenas as 100 bordas.

As médias ON/OFF seguem próximas de um ciclo de 5 ms. Esta execução apresentou
dispersão maior que a referência analógica anterior; um ensaio por condição
não demonstra ganho nem regressão consistente de desempenho.

[JSON original](loopback-analogico-otimizacoes-2026-10-11.json) e
[captura original](../screenshots/loopback-analogico-otimizacoes-2026-10-11.png).
