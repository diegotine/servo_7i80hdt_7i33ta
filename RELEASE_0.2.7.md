# T3D Analog Velocity 0.2.7

## Correção posterior à publicação

Disponível na branch `main`: sair do modo teste mantém a posição acumulada,
usando-a como origem local do encoder real. Movimento manual continua atualizando
a posição; o erro mostrado é o da malha real, inclusive com ENABLE desligado.
A contagem física não muda, e os limites locais são deslocados para preservar
o curso permitido. Reativar o teste parte da posição atual; zerar permanece
uma ação explícita. A troca não cria demanda para alcançar a antiga posição simulada.
Testes de regressão cobrem a transição habilitada/desabilitada, movimento manual,
limites, trocas repetidas e zero explícito. A tag original `v0.2.7` é preservada.

Driver Ethernet próprio para Mesa 7i80HDT + 7i33TA, sem LinuxCNC ou HAL.
Esta publicação reúne a evolução desde a 0.1.0 e preserva o firmware atual
da HDT. O próximo ensaio será com o conjunto físico de drive, motor e encoder.

## Principais mudanças desde a publicação 0.1.0

- Telemetria e gráfico de comando/feedback por motor.
- Aceleração e desaceleração independentes: padrões de 350 e 600 RPM/s,
  com limite inicial de velocidade de 1000 RPM.
- Ciclo absoluto de 1 ms, com métricas de leitura, controle, escrita,
  atraso do escalonador, estouros de trabalho e ciclos perdidos.
- Backend compilado com Cython e núcleo C++ para temporização, estatísticas
  e planejamento de rampas assimétricas.
- Prioridade FIFO, afinidade de CPU e bloqueio da memória atual com
  diagnóstico das permissões efetivamente obtidas.
- Loopback digital e analógico, teste manual PWM/PDM e pulso de 40%.
- Monitor de períodos em executável C++/Qt separado, com log JSONL,
  prioridade normal e afinidade em outra CPU. A gravação fica fora da malha;
  o driver mantém sua instrumentação existente.
- Aba Pinout com imagem incorporada e fundo transparente.
- Relatórios de bancada e documentação do ajuste medido da rede I219-LM.

O auxiliar de política de CPU pertence à interface. A investigação adicional
do clock foi adiada pelo operador; esta publicação não acrescenta alterações
de BIOS, perfil de energia, rede ou firmware.

## Evidência e limites

No loopback analógico registrado em `loopback-20261011-191612-667.json`,
ainda com período de **2 ms**, foram medidos desvios padrão de aproximadamente
**16,8 µs ON** e **14,3 µs OFF**. Os resultados incluem rede e amostragem;
não representam o atraso exclusivo da placa nem comprovam sintonia do PID.

O período de **1 ms** é a configuração atual; a frequência alvo é de
1000 correções/s por motor quando os ciclos cabem na grade. Não é uma garantia
de tempo real rígido. Medições do conjunto completo e sintonia de PID permanecem
pendentes.

## Validação desta publicação

- Compilação Release de interface, monitor, núcleo C++ e módulos Cython.
- Testes de abertura/estabilidade da interface e IPC/log do monitor separado.
- Testes matemáticos de compatibilidade nativa, rampas e temporização.
- Preflight local sem placa: núcleo 0.2.7, SCHED_FIFO 10, CPU 5,
  memória atual bloqueada, seis módulos compilados, UID 1000,
  capacidades efetivas zeradas e `NoNewPrivs=1`.
- Nenhum teste automatizado acionou a placa ou o motor.

## Executar

Use `./iniciar.sh`; o build é `build/v0.2.7`. O título mostra a versão.
Para o monitor separado, use o botão na aba TESTES ou `./monitor-periodos.sh`.
Os logs ficam na pasta de dados do usuário, em `T3D Analog Velocity/timing/`.

Os auxiliares privilegiados são instalados por versão. Para reutilizar
FIFO/memória na nova versão, compile e execute o instalador descrito em
[TEMPORIZACAO.md](TEMPORIZACAO.md). Builds e atalhos anteriores são preservados.
