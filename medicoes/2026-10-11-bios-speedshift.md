# BIOS Dell — Speed Shift

OptiPlex SFF 7010, BIOS 1.38.0. Dell Command Configure não instalado.
Leitura diretamente pela interface de firmware Dell do kernel:
`/sys/class/firmware-attributes/dell-wmi-sysman/attributes/`.

Consulta inicial: SpeedShift Disabled; Speedstep Enabled; TurboMode Enabled;
CStatesCtrl Enabled; pending_reboot 0.

Após autorização explícita do operador, escrito somente SpeedShift=Enabled.
Leitura de volta: SpeedShift Enabled; pending_reboot 1.
Os demais parâmetros não foram gravados. Nenhum reboot automático foi executado.
Boot preparado com intel_pstate=active, a ser validado após reiniciar.
