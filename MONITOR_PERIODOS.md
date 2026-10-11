# Monitor de períodos — aplicativo separado

Na aba **TESTES**, clique em **Abrir monitor de períodos e log** antes do ensaio.
Também pode usar o atalho **Monitor de períodos T3D v0.2.7** ou executar
`./monitor-periodos.sh`. O monitor é um executável C++/Qt independente:
`build/v0.2.7/t3d_timing_monitor`. Fechá-lo não interrompe o controlador.

O processo usa prioridade normal e tenta fixar-se na primeira CPU permitida
diferente da CPU configurada para o controlador. Nesta máquina, com o ajuste
padrão, monitor na CPU 0 e controlador na CPU 5. A janela informa falhas de
afinidade; não modifica clock, BIOS, perfil de energia ou rede. Não precisa de root.

## Como coleta

O controlador já mede cada ciclo e acumula estatísticas. Seu código não foi
alterado para este log. A interface encaminha a telemetria existente, cerca de
20 mensagens/s, a um socket Unix local sem bloqueio. Se o monitor não estiver
aberto ou estiver ocupado, o envio é descartado, sem espera ou confirmação.
O monitor não acessa a Mesa, não cria outra sessão UDP e não envia comandos.

Os timestamps são os do controlador. Medir o intervalo de chegada das mensagens
em outro núcleo mediria a entrega da telemetria, não o período da malha.
Os contadores acumulados preservam os totais entre mensagens recebidas.
Não se pode prometer influência absolutamente zero: a interface faz um envio
local por mensagem, e os processos ainda compartilham recursos do sistema.
O trabalho de gravação e apresentação fica fora da malha.

## O que mostra

- **Período observado**: intervalo entre inícios de ciclos, incluindo o efeito de
  comunicação, cálculo, telemetria e escalonamento entre esses inícios.
- **Atraso ao despertar**: atraso em relação ao instante agendado pelo temporizador.
- **Leitura, controle/comandos e escrita**: estatísticas dos trechos já medidos.
- **Trabalho total**: leitura até confirmação da escrita; não inclui a
  serialização/envio da telemetria posterior à escrita.
- **Estouros de trabalho**: quantidade de ciclos com esse trabalho maior que 1 ms.
- **Ciclos perdidos**: slots da grade de 1 ms descartados pelo temporizador.

Um intervalo isolado ligeiramente acima de 1 ms pode ser jitter entre despertares;
não é contado automaticamente como estouro de trabalho ou slot perdido.
O P95 usa os últimos 256 ciclos; mínimos, médias, desvios e máximos recebidos
referem-se à sessão do controlador desde a conexão/rearme. O monitor não consegue
reconstruir timestamps individuais de estouros a partir dessas estatísticas.
Uma falha antes de concluir a amostra pode não incrementar o contador de trabalho;
a mensagem de falha recebida fica registrada separadamente.

Os totais **Neste ensaio** começam na primeira mensagem válida recebida, ou
na última amostra disponível ao clicar em **Novo ensaio / novo log**.
Conexão/rearme estabelece uma nova base, preservando os totais já observados.
Ciclos anteriores à primeira amostra de cada segmento não entram nesses totais;
os contadores integrais recebidos também ficam no arquivo para conferência.
Ausência de mensagens marca os valores como históricos, nunca como ciclo zero.

## Arquivos

Logs JSONL são gravados em:

```text
~/.local/share/HL-T3D-RABN/T3D Analog Velocity/timing/
```

Cada arquivo tem abertura, resumo por segundo, eventos quando os contadores de
estouro/perda aumentam, falhas recebidas e encerramento normal. Contém o JSON
original de telemetria, PID da interface/controlador, versão e horário UTC de
observação. Esse horário é o de recepção; não é o timestamp de uma borda elétrica.
O botão **Abrir pasta dos logs** permite localizar os arquivos. Um encerramento
forçado pode deixar o último resumo como registro final.

## Medição com drive, motor e encoder reais

Abra o monitor antes do ensaio, conecte pelo aplicativo principal e confirme
os ajustes do motor conforme o README. Use **Novo ensaio / novo log** para
estabelecer uma referência antes de iniciar os movimentos. Ao concluir,
encerre normalmente o monitor para salvar o resumo final.

O monitor apenas observa o modo executado pelo controlador. Com motores
desabilitados, a leitura e conversão dos encoders continuam, mas o PID retorna
antes de calcular a correção. No modo teste de saída, o PID também é contornado.
Essas situações não medem o custo da malha fechada ativa. O número de motores
habilitados e o modo de cada eixo ficam na telemetria gravada para contextualizar
os tempos. A maior frequência de pulsos carrega o contador da FPGA, sem aumentar
o número de mensagens Ethernet por ciclo.
