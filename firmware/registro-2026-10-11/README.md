# Firmware gravado — 2026-10-11

- Placa identificada pela rede: 7I80HDT, IP 192.168.1.121.
- Fonte oficial: https://www.mesanet.com/software/parallel/7i80hdt.zip
- Arquivo: 7i80hdt_sv12d.bin; 678650 bytes.
- SHA256: 1b1daff47787c8427d819dd18b7bf874afb5c6b4e2f178fd2cbc5b4c89205653.
- Fonte de pinagem: PIN_SV12D_72.vhd e 7i80hdt_sv12d.pin no pacote oficial.
- Mesaflash compilado localmente do LinuxCNC/mesaflash, commit 11e6f8571cc79d3acae57274aa57c4b99d26cb3f, Ethernet MESAFLASH_IO=0.
- Gravação na área de usuário: sucesso; verificação automática: sucesso; reload: sucesso.
- Sem backup de flash, por instrução explícita do operador.
- Inventário após reload: 12 PWM e 12 QCount. P3 mapeia canais 8,9,10,11 para a única 7i33TA.
- ENABLE após reload: 0. DDR das três portas após reload: 0 (entradas).
- Aplicativo: P3 para servo; P1/P2 GPIO com 12 entradas e 12 saídas inicialmente baixas, aplicadas ao conectar. Ao sair, volta a entradas.
- Sem ENABLE ou movimento durante a gravação/conferência. Leituras de encoder sob movimento e tensão analógica ainda não testadas.
