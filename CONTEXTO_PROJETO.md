# Contexto de continuidade — 11/10/2026

Resumo conferido nos arquivos locais do projeto; consultar README.md, PINOUT.md
e TESTE_LOOPBACK.md para os detalhes técnicos.

## Hardware e identificação dos conectores

- Mesa 7i80HDT, IP inicial 192.168.1.121, firmware 7i80hdt_sv12d.bin.
- O código, config.example.json, PINOUT.md e o registro de firmware usam P3
  da HDT para a única 7i33TA, com canais HostMot2 8–11; P1/P2 são GPIO.
- Operador confirmou em 11/10/2026: a placa está no **conector P3 da HDT**.
  A indicação anterior “TB3” se referia a P3, não a outro borne.
- O manual local da 7i33TA identifica seus bornes de sinais como TB1 e TB2,
  e o conector do cabo de 50 vias como J1. A ligação de loopback documentada
  se refere a esses bornes, não ao flat da HDT.
- Drive T3D em modo velocidade, comando ±10 V; escala inicial 3000 RPM
  a 10 V e encoder inicial 10000 contagens/volta, sujeitos à conferência real.

## Aplicativo e estado local

- Interface C++20/Qt6 Widgets em app/; arquivos .ui editáveis no Qt Designer.
- Driver Ethernet LBP16 próprio em driver/mesa7i80hdt.py, sem LinuxCNC/HAL.
- Controlador de trajetória/PID em driver/servo.py; backend.py é o único
  proprietário da comunicação da sessão. Ciclo nominal 2 ms, prazo 20 ms,
  watchdog 100 ms; sem garantia de tempo real rígido ou infraestrutura RTAPI.
- Versão local 0.2.4 em desenvolvimento, conforme CMakeLists.txt e CHANGELOG.md.
  Há alterações locais ainda não publicadas; não confundir com release público.
- Recursos locais: ajustes com placa conectada, limite padrão 3000 RPM,
  saída ±10 V, JOG com retenção, STOP mantendo ENABLE, modo teste com
  posição virtual e encoder real, gráfico de comando/feedback e diagnóstico.
- Aba TESTES implementa loopback digital ENA → A, 100 ciclos, médias ON/OFF,
  dispersão e exportação de amostras JSON. Validação física está pendente.
- Loopback analógico 0/+4 V implementado; validação física pendente. Operador
  pretende ligação direta. Documentação distingue o comando limitado da
  proteção elétrica: entrada TTL não é especificada para a faixa ±10 V.

## Próximos passos acordados

Medição manual de saída informada pelo operador: 0% = −0,0022 V; 25% = 2,5330 V;
50% = 5,0671 V; 75% = 7,563 V; 100% = 10,064 V. Registro em
medicoes/2026-10-11-saida-analogica.md. Offset observado em zero: −2,2 mV.
Isso confirma a relação de magnitude positiva, sem validar ligação direta
de DRV ao encoder ou implementar compensação de offset no aplicativo.
Osciloscópio: operador informou 5,12 V e rise time 162,40 µs, trigger 2,5 V.
Revisão do código: loopback analógico tem amplitude fixa +4 V (40%), independente
do campo PWM/PDM manual. Exige A em zero estável por 50 ms antes do pulso;
sem retorno conectado, A flutuante pode impedir a aplicação. Interface e ajuda
agora explicitam essa espera. Amplitude reduzida de +5 V para +4 V por solicitação do operador.
Botão Pulso 40% / 500 ms acrescentado para captura com osciloscópio sem
retorno conectado: aplica +4 V, depois zero e ENABLE desligado. Não depende
da confirmação inicial de A e não calcula latência.
Operador confirmou funcionamento do botão de pulso; pico informado de 4,46 V
para comando de 40%. Tensão de patamar e condições da ponta ainda pendentes.

1. Loopback digital medido: ON 4,933 ms, OFF 4,940 ms, 100 ciclos; desvios
   0,050/0,048 ms. Prioridade atual: teste manual de magnitude PWM/PDM para
   medir relação com tensão, sem retorno conectado ao encoder. Depois medir
   o loopback analógico.
2. Versão 0.2.2 implementada: temporizador absoluto nativo, horários vencidos
   pulados, métricas de ciclo/fases, afinidade de CPU, tentativa SCHED_FIFO 10
   e MCL_CURRENT; resultado real aparece em HDT • Diagnóstico. Coleta cíclica
   automática Python suspensa durante controle. Sem migração do PID para C/C++.
   Operador pediu não executar simulação nesta etapa; medição real pendente.
   Limite RTPRIO observado no ambiente: 0; MEMLOCK: 16 MiB. Permissões não alteradas.
   Referência anterior preservada em commit f70f067; versão subida em 604bcb6.
   Detalhes em TEMPORIZACAO.md.
3. Calibração de offset será executada pelo próprio drive, eventualmente
   acionada por Modbus ou painel; não adicionar compensação no software.

Não acionar hardware durante manutenção de documentação. Testes simulados
não comprovam a latência, a ligação elétrica ou a sintonia do conjunto real.

## Correção de numeração e medição das otimizações

Operador determinou que a versão com otimizações é **0.2.2**, e não 0.2.1.
Captura e JSON da medição original preservados sem alterar o rótulo 0.2.1.
100 ciclos analógicos: ON 4,98157029 ms, OFF 4,97217125 ms; desvios
0,103568251 ms e 0,089186910 ms. CPU 5 aplicada; SCHED_OTHER / prioridade 0;
MCL_CURRENT falhou com Cannot allocate memory; FIFO negado por permissão.
Ciclo médio real 5,000008561 ms; zero horários pulados nessa sessão.
Atalho novo Iniciar T3D v0.2.2.desktop criado; anteriores preservados.

## Atualização 0.2.3

- Ciclo de 2 ms; contagem de trabalho acima do período e horários pulados no diagnóstico.
- Auxiliar de limites instalado via autenticação Polkit; checagem real sem placa confirmou SCHED_FIFO 10, CPU 5 e mlockall(MCL_CURRENT).
- Backend mantém UID 1000, sem capabilities após o auxiliar. Interface não roda como root.
- Sem execução de placa simulada por solicitação do operador; medição física de 2 ms pendente.

### Correção posterior à primeira medição 0.2.3

- Loopback físico: ON/OFF ~1,939 ms; 16.793 ciclos, nenhum horário pulado ou trabalho acima de 2 ms. FIFO 10 funcionou; mlock falhou nessa sessão.
- Causa: locale-archive de 223 MiB + thread/módulos elevavam mapas acima do limite de 256 MiB.
- Auxiliar atualizado força LC_ALL=C/PYTHONUTF8=1; checagem com módulos e thread confirmou ~100 MiB bloqueados, FIFO 10 e UID 1000.
- Sudoers restrito instalado por pedido do operador; auxiliares abandonam root e capabilities antes do backend. Nova medição física pendente, sem interrupção do processo existente.

## Atualização 0.2.4 — Cython

- Antes da conversão: referência física 0.2.3 com mlock/FIFO confirmados, 10.399 ciclos sem estouros; intervalo médio 2,000002 ms, desvio 3,807 µs.
- Cinco módulos compilados pelo CMake: backend, servo, mesa7i80hdt, loopback, timing.
- driver/servo.py é fonte oficial; servo.pxd declara campos numéricos C, mantendo contagem de encoder como inteiro Python ilimitado.
- Aplicativo exige extensões carregadas, registra native_servo=true e caminhos dos .so. Mantém 2 ms, watchdog, escala, pinagem e ganhos.
- Pacotes oficiais Fedora python3-cython e python3-devel instalados; Python atualizado pela dependência para 3.14.8, Cython 3.2.4.
- Auxiliar/sudoers existente compatível: backend.py delega ao backend compilado antes de qualquer I/O.
- Qt .ui permanece editável. Atalho 0.2.4 criado; anteriores preservados. Comparação física Cython pendente.
