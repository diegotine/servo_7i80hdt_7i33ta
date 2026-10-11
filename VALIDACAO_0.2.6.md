# 0.2.6 — política de CPU pertencente à interface

A interface Qt controla a sessão de clock pelo auxiliar nativo `t3d_cpu_policy`.
O fechamento da interface encerra seu canal, disparando a restauração no
auxiliar. Nenhum código de clock é compilado no `t3d_runtime_limiter` ou nos
módulos do driver. O auxiliar do runtime continua concedendo FIFO/memória e
abandonando privilégios antes de executar o backend.

O instalador grava os dois auxiliares root e regras sudoers restritas com
versão no nome. O build atual é `build/v0.2.6`; os binários anteriores da 0.2.5
foram preservados. O iniciador determina a versão pelo CMakeLists.txt.

Validação sem placa em 11/10/2026:

- Compilação C++ concluída; avisos preexistentes de Cython permanecem.
- `gui_smoke`, `native_compatibility` (6 casos) e `native_motion` passaram.
- Preflight instalado confirmou núcleo 0.2.6, FIFO 10, CPU 5, memória bloqueada,
  seis módulos nativos, UID 1000, capacidades zero e `NoNewPrivs=1`.
- Novo auxiliar de CPU: sessão temporária na CPU 4 confirmou min=max 4200000,
  governador/EPP preservados e restauração para os valores anteriores. A CPU 5
  segue com a sessão da instância 0.2.5 aberta pelo operador.

## Clock observado

CPU 5 manteve os limites 4200000/4200000. A leitura por
`x86_energy_perf_policy` confirmou HWP min=max 54, EPP 128. Em baixa carga,
`turbostat` mediu Bzy_MHz 1579..1857; teste temporário de governador performance
e EPP 0 não estabilizou esse indicador em 4200. Os ajustes foram restaurados.
Não foi identificado outro processo sobrescrevendo os limites. Ainda falta
determinar a causa da frequência efetiva e medir durante a malha real.

## C-states

Leitura pela interface Dell da BIOS: CStatesCtrl Enabled, com opções apenas
Disabled/Enabled; não há seleção numérica de C1 nesse atributo. DeepSleepCtrl
Disabled, SpeedShift Enabled, pending_reboot 0. Nenhuma gravação na BIOS.

Linux: driver ativo `intel_idle`, parâmetro `max_cstate=1`, estados disponíveis
POLL e C1_ACPI. Assim, o limite efetivo exposto pelo driver é C1. O parâmetro
`processor.max_cstate=8` é de outro driver, que não está ativo nesta máquina.
