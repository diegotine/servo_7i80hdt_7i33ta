# BIOS Dell — C-states desabilitados

Alteração solicitada pelo operador, confirmando que “save state em zero”
significa desabilitar C-states da CPU.

Dell Command Configure não está instalado. A gravação utilizou a interface
oficial do kernel Dell `dell-wmi-sysman`, no atributo `CStatesCtrl`.

- Valor anterior lido: `Enabled`.
- Valor gravado e relido: `Disabled`.
- `pending_reboot` após a gravação: `1`.

Nenhuma alteração adicional em Turbo, Speed Shift, clock, kernel ou rede.
Não foi feita reinicialização automática. O Linux em execução ainda expõe
`intel_idle.max_cstate=1`; a confirmação na BIOS não demonstra que o sistema
atual esteja exclusivamente em C0. A aplicação e a medição efetiva após
reiniciar ficam pendentes, sem alegação de redução de jitter neste registro.
