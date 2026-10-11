# Volume de dados e capacidade estimada da malha

Este documento registra a previsão baseada no ensaio de 2 ms. Posteriormente,
o operador solicitou e recebeu a 0.2.6 atualizada para 1 ms; a medição física
nesse novo período ainda está pendente.

Cálculo em 11/10/2026 para o código 0.2.6 e o JSON
`loopback-20261011-191612-667.json`, ensaio analógico após ajuste da rede.
Nenhum período ou parâmetro do aplicativo foi alterado para esta análise.

## Dados por ciclo, quatro motores

A FPGA conta os pulsos dos encoders; o computador recebe registros acumulados,
não um pacote por pulso. Equações de trajetória, velocidade, erro e PID são
calculadas localmente e não acrescentam dados recebidos pela Ethernet.

`read_encoders()` consulta quatro registros de contagem, quatro de controle,
três portas GPIO, watchdog e cookie: 13 leituras de 32 bits. Cada comando LBP16
ocupa quatro bytes. A leitura recebe 52 bytes, dos quais 16 são registros de
contagem dos quatro encoders; apenas os 16 bits inferiores de cada registro
são contagem de posição, como implementado no driver.

`write_servo()` envia quatro referências analógicas, máscara ENABLE, duas
portas de saída e alimentação do watchdog: oito escritas de oito bytes.
`_commit()` acrescenta duas leituras de quatro bytes para watchdog e cookie,
com resposta de oito bytes. Não usa o método genérico `Lbp16.write()`.

| Transação | PC → placa | Placa → PC |
|---|---:|---:|
| Leitura dos encoders e estado | 52 bytes | 52 bytes |
| Escrita das saídas e confirmação | 72 bytes | 8 bytes |
| Total por ciclo | 124 bytes | 60 bytes |

Total LBP16: 184 bytes/ciclo em quatro datagramas UDP, dois em cada direção.
Exclui descoberta, configurações ocasionais, ARP e telemetria local da GUI.
Os tamanhos já incluem os quatro motores e P1/P2; não devem ser multiplicados
por quatro ao estimar a banda de rede.

Com IPv4 sem opções, UDP, Ethernet sem VLAN, FCS, padding mínimo, preâmbulo e
intervalo entre quadros, o orçamento é:

```
quadro(P) = max(64, 14 + 20 + 8 + P + 4) + 8 + 12
quadro(52) + quadro(52) + quadro(72) + quadro(8)
          = 118 + 118 + 138 + 84 = 458 bytes equivalentes por ciclo
```

Em 100 Mb/s são 36,64 µs de serialização agregada. Isso não inclui o tempo de
processar transações, interrupções, sockets e escalonamento; não é a latência
total da malha. O link é full duplex, portanto as capacidades de cada direção
são separadas. A soma de tráfego abaixo é apenas um orçamento agregado.

| Período | Ciclos/s por eixo | Entrada LBP16 no PC | Tráfego no fio, soma das direções |
|---|---:|---:|---:|
| 2 ms | 500 | 30 kB/s | 1,832 Mb/s |
| 1,5 ms | 667 | 40 kB/s | 2,443 Mb/s |
| 1 ms | 1000 | 60 kB/s | 3,664 Mb/s |
| 0,75 ms | 1333 | 80 kB/s | 4,885 Mb/s |
| 0,5 ms | 2000 | 120 kB/s | 7,328 Mb/s |

A 1 ms, são 16 kB/s dos registros de contagem, incluídos nos 60 kB/s totais de
entrada LBP16. Mesmo a 0,5 ms, a banda do link não é o limite principal.

Exemplo com 10000 contagens por volta, padrão configurado, e 3000 RPM:
500000 contagens/s por encoder, ou 2000000 para quatro. A 2 ms, cada eixo pode
avançar cerca de 1000 contagens entre leituras, mas os pacotes mantêm o mesmo
tamanho. Essa contagem é feita na FPGA, não por interrupção de CPU a cada pulso.

## Tempos medidos

O JSON contém 571949 ciclos acumulados, cerca de 19,1 minutos. As médias e
máximos são de toda a sessão, que pode incluir estados anteriores ao ajuste
de rede; o P95 recente é da janela final de 256 ciclos, cerca de 0,512 segundo.

| Etapa | Média acumulada | P95 recente | Máximo acumulado |
|---|---:|---:|---:|
| Leitura | 0,271616 ms | 0,206159 ms | 0,869856 ms |
| Controle e tarefas entre leitura/escrita | 0,012424 ms | 0,021982 ms | 0,217880 ms |
| Escrita e confirmação | 0,189850 ms | 0,176516 ms | 0,650640 ms |
| Trabalho completo até confirmar a saída | 0,473891 ms | 0,407510 ms | 1,312303 ms |
| Atraso ao despertar | 0,009033 ms | 0,024210 ms | 2,422450 ms |

O trabalho é tempo de parede: inclui espera de rede e não equivale a uso de CPU.
O P95 do total é medido diretamente; somar P95s das etapas não produz o P95 do
total. O intervalo máximo entre ciclos foi 4,418779 ms. Houve zero work_overruns
no período atual de 2 ms e um skipped_slot na sessão acumulada.

Limitação importante: durante o loopback, os eixos ficam desabilitados e
`Axis.calculate()` retorna antes do PID. Os 12,4 µs médios e 22,0 µs de P95
não são uma medição de quatro PIDs completos em movimento. O feedback dos
quatro encoders e o mesmo tráfego cíclico de rede já estão presentes.

O temporizador de trabalho termina antes de produzir as estatísticas e o JSON
periódico de telemetria. Essas tarefas, o custo adicional do PID ativo e o
escalonamento também precisam caber no período. Não há medição isolada atual
que permita atribuir um tempo exato a quatro PIDs ativos.

## Previsão e próximo ensaio

Para planejamento, usar 0,407510 ms do trabalho recente e reservar mais 0,100 ms
para o caminho ativo e tarefas auxiliares: orçamento aproximado de 0,508 ms.
A reserva é uma hipótese de engenharia, não uma medição nem limite garantido.
Também não cobre necessariamente as caudas de atraso do escalonador.

| Período | Correções/s por motor | Atualizações de eixo/s, quatro motores | Orçamento de 0,508 ms / período |
|---|---:|---:|---:|
| 2 ms | 500 | 2000 | 25,4% |
| 1,5 ms | 667 | 2667 | 33,8% |
| 1 ms | 1000 | 4000 | 50,8% |
| 0,75 ms | 1333 | 5333 | 67,7% |
| 0,5 ms | 2000 | 8000 | 101,5% |

Há evidência para ensaiar 1 ms como próximo alvo: dobra a taxa por motor e deixa
aproximadamente metade do período nesse orçamento. 0,75 ms é um candidato
posterior, condicionado à medição. 0,5 ms já consome todo o orçamento estimado.
O inverso do tempo típico de trabalho não define uma taxa sustentável garantida.

O máximo acumulado de trabalho de 1,312303 ms excede 1 ms, e o atraso máximo
ao despertar também excede esse período. Não é possível garantir todos os
prazos de 1 ms a partir deste ensaio. É necessário iniciar uma sessão limpa
após o ajuste de rede e comparar trabalho, despertar e slots pulados ao reduzir
o período; depois medir com os quatro eixos/PIDs ativos e telemetria normal.
O PID já usa dt real, mas maior taxa não garante melhor controle sem avaliar
ruído do encoder, atraso total e sintonia física.

## Referências

- Código local: driver/mesa7i80hdt.py, métodos read_encoders, write_servo e _commit.
- Código local: driver/backend.py, Session.step; driver/servo.py, Axis.calculate.
- [Formato Ethernet/IPv4/UDP e overhead, ODVA](https://www.odva.org/wp-content/uploads/2022/03/2022-ODVA-Conference_Evaluating-TSN-Preemption-for-Cyclic-EtherNetIP-Communication_Blair_FINAL.pdf).
- [LinuxCNC hm2_eth: requisitos de temporização e interface Ethernet](https://linuxcnc.org/docs/master/html/man/man9/hm2_eth.9.html).
