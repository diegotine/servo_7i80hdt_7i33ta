# Temporização — 0.2.3

O período nominal da 0.2.3 é **2 ms (500 Hz)**; na referência 0.2.2 era 5 ms. O PID usa o intervalo real
entre inícios de ciclos, não uma constante de 2 ms nem a média do loopback.
Limite de ciclo/processamento: 20 ms; watchdog da HDT: 100 ms;
heartbeat da interface: 500 ms. Esses limites não foram relaxados.

## Alterações

- Espera nativa com `clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME)` via
  biblioteca C do Linux. Cada início pertence à mesma grade temporal, em vez
  de somar 2 ms ao instante efetivo do último ciclo. Interrupção por sinal
  retoma a espera pelo mesmo instante absoluto.
- Horários já vencidos são descartados; não há uma sequência de ciclos
  imediatos para compensar atrasos. O intervalo real continua sujeito ao
  limite de 20 ms e é usado pelo controlador.
- Coleta automática de referências cíclicas Python suspensa durante a sessão
  de controle. A liberação normal por contagem de referências continua ativa.
  Coleta explícita ocorre fora do ciclo, após solicitar desligamento na falha;
  o estado anterior da coleta automática é restaurado ao sair.
- Afinidade do thread de controle com uma CPU permitida e tentativa de
  prioridade SCHED_FIFO 10. O leitor de comandos é criado antes desses ajustes,
  mantendo seu próprio escalonamento e afinidade; a interface é outro processo.
- Tentativa de `mlockall(MCL_CURRENT)` para as regiões de memória existentes.
  Novas alocações Python não são garantidas como bloqueadas. Não se usa
  MCL_FUTURE. O auxiliar opcional concede limites apenas ao backend.

Erros de permissão ficam no histórico, e a aba **HDT • Diagnóstico** mostra
o escalonador, prioridade, CPUs e bloqueio de memória efetivamente obtidos.
SCHED_OTHER / prioridade 0 significa execução normal; a presença do código
de otimização não significa que o sistema concedeu prioridade de tempo real.

## Métricas

O diagnóstico mostra média, desvio padrão e P95 recente do intervalo entre
ciclos, maior atraso ao despertar, horários pulados e médias de leitura,
cálculo/comandos e escrita com confirmação. A exportação JSON do loopback
inclui `timing` e `runtime` com detalhes adicionais e os ajustes efetivos.

Mínimos, máximos, médias e desvios são acumulados na sessão; P95 usa somente
as últimas 256 amostras de cada grandeza. As métricas reiniciam ao rearmar. O contador `work_overruns` conta ciclos
cuja leitura + cálculo + escrita ultrapassaram 2 ms; isso não muda o limite
de falha de 20 ms. Custos de telemetria também podem causar horários pulados,
mesmo que o trabalho de I/O esteja abaixo do período.
O tempo de trabalho inclui leitura, cálculo e escrita; não inclui a montagem
e transmissão da própria telemetria. Esse custo aparece no intervalo real
do ciclo seguinte. A medição de leitura inclui a ida e volta UDP; não é
uma medição isolada do encoder ou da FPGA.

Os tempos ON/OFF do loopback seguem o mesmo critério da 0.2.0. Não subtrair
automaticamente um ciclo, nem somar a média ON/OFF como atraso adicional no
PID. Não foram alterados os ganhos PID, a escala analógica ou a pinagem.

## Opções de execução

Os padrões são aplicados pelo backend, incluindo quando aberto pela interface.
Para comparar ajustes, variáveis de ambiente podem ser passadas ao iniciador:

```sh
# Temporizador absoluto e métricas, com escalonamento/afinidade normais:
T3D_RT_PRIORITY=0 T3D_CPU=none T3D_MLOCK=0 ./iniciar.sh

# Padrões da 0.2.3: tentativa FIFO 10, última CPU permitida, memória atual:
./iniciar.sh
```

`T3D_RT_PRIORITY`: 0 ou 1–50. `T3D_CPU`: `auto`, `none` ou índice de CPU
permitida. `T3D_MLOCK`: `1` para tentar ou `0` para não tentar.
A afinidade não reserva nem isola a CPU de outros processos ou interrupções.
A interface continua executando como usuário normal. Para conceder os limites
necessários ao backend, compile e execute uma vez:

```sh
pkexec /usr/bin/bash "$PWD/instalar-limites-tempo-real.sh"
```

O instalador pede autenticação do Linux e cria um executável pertencente a root
em `/usr/local/libexec/t3d-analog-runtime-<UID>`, com `cap_sys_resource=ep`.
Esse auxiliar concede prioridade máxima 20, memória bloqueada até 256 MiB e
limite de 200 ms de CPU RT sem bloqueio. Depois remove todas as capabilities e
ativa `NO_NEW_PRIVS` antes de executar o backend, com o UID do usuário.
Não atribui capabilities ao Python nem altera limites globais ou o kernel.
O instalador também cria `/etc/sudoers.d/t3d-analog-<UID>`, validado com
`visudo`, autorizando sem senha somente esse auxiliar fixo. A interface verifica
a autorização com `sudo -n -l` e usa `sudo -n` na próxima conexão. O auxiliar
concede os limites e abandona root antes de executar Python. Sem a regra,
continua disponível a execução direta com a capability restrita.
Se ele não estiver instalado, usa o backend comum e informa as permissões negadas.
Reinstale após mover o projeto: os caminhos do backend e do Python são fixados
na compilação. O auxiliar só aceita o UID usado na compilação.

Verificação sem comunicação com a placa:

```sh
/usr/local/libexec/t3d-analog-runtime-$(id -u) --check
```

O backend usa `LC_ALL=C` e `PYTHONUTF8=1`, sem alterar o idioma da interface.
Isso evita mapear `/usr/lib/locale/locale-archive` (223 MiB neste computador),
que, somado às demais regiões e à thread leitora, excedia 256 MiB. A checagem
agora importa os módulos reais do backend e cria uma thread antes de bloquear
memória, sem abrir UDP nem construir a placa. A falha foi reproduzida com o
auxiliar antigo; após a correção, cerca de 100 MiB foram bloqueados.

Neste computador, a verificação real via sudoers confirmou **SCHED_FIFO 10**, CPU 5,
memória atual bloqueada, UID 1000, capabilities efetivas zeradas e
`NO_NEW_PRIVS=1`, sem avisos. Isso funciona neste kernel comum; a qualidade da
temporização de 2 ms ainda será medida na bancada.

## Comparação na bancada

Referência da 0.2.0 em `medicoes/2026-10-11-loopback-referencia.md`, com JSONs
originais e screenshots. Repetir o mesmo canal, ligação, amplitude e condições
de carga/rede. Comparar a dispersão, P95, máximos e horários pulados, além das
médias ON/OFF. Primeira medição do código otimizado registrada em
[medicoes/2026-10-11-loopback-otimizacoes.md](medicoes/2026-10-11-loopback-otimizacoes.md),
com rótulo original 0.2.1 antes da correção para 0.2.2. Nessa execução, afinidade
foi aplicada, mas prioridade RT e bloqueio de memória foram recusados.
Melhoria de latência ainda depende de comparação sob condições controladas.

A 0.2.3 foi compilada e conferida sem executar a placa simulada, por solicitação
do operador. Os novos testes de regressão estão disponíveis para execução
posterior; não foram executados nessa entrega. A abertura Qt sem placa e a
verificação de sintaxe não validam temporização ou movimento físico.

O controlador de trajetória/PID continua em Python. Esta versão não reproduz
integralmente RTAPI e não garante tempo real rígido em kernel comum. A espera
é nativa, mas não houve migração da malha de controle para C/C++.

Referências: [clock_nanosleep](https://man7.org/linux/man-pages/man2/clock_nanosleep.2.html),
[mlockall](https://man7.org/linux/man-pages/man2/mlockall.2.html),
[escalonamento e afinidade em Python](https://docs.python.org/3/library/os.html#interface-to-the-scheduler).
