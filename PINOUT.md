# Pinagem confirmada — 7i80HDT + 7i33TA

Conferida pelo operador em 11/10/2026.
Placa: 7i80HDT, IP 192.168.1.121.
Firmware gravado: 7i80hdt_sv12d.bin.

O arquivo `pinout_7i80hdt_sv12d.pin` contém o inventário completo lido da placa
pelo mesaflash após a gravação. As funções secundárias descritas nele são as
possibilidades do firmware; P1/P2 são selecionados como GPIO pelo nosso driver.

## P1 e P2 — I/O genérico

Em cada conector:

- 12 entradas: pinos físicos 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23.
- 12 saídas: pinos físicos 25, 27, 29, 31, 33, 35, 37, 39, 41, 43, 45, 47.
- POWER: pino 49; tensão conforme o jumper da placa.
- Terra: todos os pinos pares, de 2 a 50.

P1: entradas IO0–IO11; saídas IO12–IO23.
P2: entradas IO24–IO35; saídas IO36–IO47.

A divisão é aplicada ao conectar o aplicativo. As saídas começam em nível baixo.
Ao desconectar, voltam a entradas. Interfaces de 24 V exigem adaptação elétrica.

## P3 — única 7i33TA

Conectar P3 ao J1 da 7i33TA com cabo de 50 vias, respeitando o pino 1.
Os quatro canais locais correspondem aos canais HostMot2 8, 9, 10 e 11.

- Motor 1 / canal local 0: encoder A pino 7, B pino 5, Z pino 11; PWM pino 15, DIR pino 19, /ENABLE pino 23.
- Motor 2 / canal local 1: encoder A pino 3, B pino 1, Z pino 9; PWM pino 13, DIR pino 17, /ENABLE pino 21.
- Motor 3 / canal local 2: encoder A pino 31, B pino 29, Z pino 35; PWM pino 39, DIR pino 43, /ENABLE pino 47.
- Motor 4 / canal local 3: encoder A pino 27, B pino 25, Z pino 33; PWM pino 37, DIR pino 41, /ENABLE pino 45.

Os números acima são pinos físicos do P3 da 7i80HDT, não bornes da 7i33TA.

## CN1 do T3D — 12 condutores mais blindagem por drive

- 26 — AS+: comando analógico.
- 10 — AS−: retorno do comando analógico.
- 11 — GNDA: referência analógica.
- 13 — OA+: encoder A+.
- 28 — OA−: encoder A−.
- 14 — OB+: encoder B+.
- 29 — OB−: encoder B−.
- 15 — OZ+: índice Z+.
- 30 — OZ−: índice Z−.
- 12 — GND: referência do encoder.
- 16 — DI1/SON: habilitação, conforme configuração do drive.
- 31 — COM+: alimentação das entradas digitais, 24 V.

SON exige interface compatível entre ENABLE de 5 V da 7i33TA e circuito de 24 V
do T3D. RDY/ALM não são utilizados nesta configuração; diagnóstico pelo encoder.
CCWL/CWL, reset de alarme e freio não estão incluídos nesses 12 fios; conferir
as necessidades da máquina e a configuração real das entradas antes da montagem.

Diagrama frontal do CN1: `diagramas/CN1_T3D_frente_macho.pdf`.
Fontes: `reference/7i80hdtman.pdf`, `reference/7i33man.pdf` e
`reference/T3D_Debugging_Manual_V2.3_CN.pdf` (PDF 6 / página impressa 3).
