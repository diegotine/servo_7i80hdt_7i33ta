# Otimização 0.2.5 — estado de desenvolvimento

A versão foi incrementada antes das mudanças. Ciclo nominal 2 ms, prazos,
watchdog, protocolo Ethernet e PID preservados. Ainda não há uma medição física
da 0.2.5 que comprove redução do desvio.

## Núcleo nativo e controles

`native/rtcore.cpp` implementa temporizador absoluto CLOCK_MONOTONIC,
estatísticas Welford e janela fixa de 256 amostras. `native/motion.hpp` contém
rampas e planejamento com aceleração/desaceleração independentes.
A ordenação para P95 ocorre apenas ao solicitar relatório.
O backend continua em Cython; esta é uma migração incremental, não uma
reescrita completa em C++.

Valores iniciais: limite e JOG 1000 RPM; aceleração 350 RPM/s; desaceleração
600 RPM/s. STOP mantém ENABLE e usa a desaceleração. Escala física continua
3000 RPM a 10 V. Configurações explicitamente carregadas são preservadas.

Validação realizada: compilação Release sem novos avisos, regressões C++ de
rampas assimétricas/reversão/continuidade/limites, seis testes de compatibilidade,
sete verificações de temporização e interface Qt offscreen. Nenhuma placa ou
planta simulada foi executada nessa validação.

## Referências e aplicação

Skills Intel `performance-patterns` e `linux-perf` instaladas. Foi aplicado o
fluxo de revisão por código-fonte de performance-patterns. Não houve coleta com
perf nem alegação de ganho com base apenas no código.

- https://github.com/intel/intel-performance-skills
- https://github.com/redhat-performance/tuned/blob/master/tuned/plugins/plugin_cpu.py
- https://github.com/redhat-performance/tuned/blob/master/tuned/plugins/plugin_sysfs.py
- https://github.com/redhat-performance/tuned/blob/master/profiles/latency-performance/tuned.conf
- https://docs.kernel.org/admin-guide/pm/intel_pstate.html

TuneD consultado como referência de funcionamento; nenhum trecho Python foi
copiado para o núcleo nativo. CPU plug-in: governor, EPB/EPP, boost, PM QoS.
Sysfs plug-in: salvar, gravar, verificar e restaurar configurações.

O helper root instalado tem uma sessão separada de CPU, sem executar código do
usuário como root. A interface solicita ajustes ao abrir; EOF do canal ao fechar
ou cair dispara restauração. SIGTERM também restaura. SIGKILL do próprio helper
ou queda do sistema não permite executar a restauração. Alterações externas
posteriores são respeitadas. Instâncias concorrentes usam lock exclusivo.

Quando TuneD está ativo, a sessão `--cpu-clock-session` solicita apenas os
limites mínimo/máximo de 4200 MHz da CPU dedicada. Governador, EPP/EPB, boost
e PM QoS permanecem sob controle do perfil TuneD. Os limites anteriores são
restaurados ao fechar. Uma mudança posterior de perfil pode substituir esses
limites; a sessão não os reaplica continuamente.

Após habilitar Speed Shift na BIOS e reiniciar, o driver é `intel_pstate` ativo
com HWP. Os governadores disponíveis são `performance` e `powersave`, sem
`userspace`; por isso o ajuste usa `scaling_min_freq`/`scaling_max_freq`, sem
`scaling_setspeed`. A leitura dos limites confirma a solicitação ao kernel,
não garante frequência física constante diante de limites térmicos/energéticos.
CPUFreq pode aplicar os pedidos de limites de forma assíncrona. O helper espera
confirmação por até 1 segundo em cada gravação, inclusive na restauração, fora
da malha de controle. Validação local em
`medicoes/2026-10-11-limites-cpu-4200mhz.md`.

## Máquina atual / solicitação de 4200 MHz

Estado anterior ao reboot: CPU i5-13500, CPU dedicada 5, acpi-cpufreq; governador originalmente schedutil,
EPB 6, PM QoS 0. Turbo habilitado. O estado 2501000 kHz representa a faixa turbo,
não um teto físico de 2501 MHz. /proc/cpuinfo mostrou 4500 MHz.

A seleção exata de 4200000 kHz não está na tabela deste driver. O helper só
confirma mínimo/máximo 4200 MHz quando o driver aceita e a leitura verifica ambos.
Caso contrário aplica performance e indica a limitação, sem alegar clock fixo.
Limites térmicos e de potência do hardware continuam valendo.

No boot atual o kernel registra:
`intel_pstate: HWP-disabled hybrid CPU is not supported`.
Leitura direta de CPUID.6 confirmou HWP=0 e HWP_EPP=0. Não há
`intel_pstate=disable` na linha de comando. Conferir Intel Speed Shift/HWP no
firmware antes de preparar mudanças de boot; adicionar `intel_pstate=active`
isoladamente não elimina a falta do recurso exposto.

TuneD 2.28.0 e tuned-gtk foram instalados a pedido do operador. Interface aberta
para seleção manual de perfil. O ensaio posterior combinou GUI 0.2.4 e núcleo
0.2.5; foi registrado com identificação explícita em medicoes/. A 0.2.4 foi
isolada em .versions/v0.2.4, com helper e atalho próprios. O novo núcleo exporta
sua versão ao JSON para evitar ambiguidade. Nenhuma
conexão/movimento da Mesa foi executada pelo Codex nessa etapa.
