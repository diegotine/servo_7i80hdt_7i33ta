# Saída analógica — medição manual em 11/10/2026

Valores informados pelo operador no teste manual de magnitude PWM/PDM.
Procedimento indicado: Motor 1, multímetro entre TB1 pino 10 (DRV0) e
TB1 pino 9 (GND). Identificação do instrumento e incerteza não registradas.

| Magnitude | Referência nominal | Tensão informada |
|---|---:|---:|
| 0% | 0 V | −0,0022 V |
| 25% | +2,5 V | +2,5330 V |
| 50% | +5 V | +5,0671 V |
| 75% | +7,5 V | +7,563 V |
| 100% | +10 V | +10,064 V |

Os pontos medidos são compatíveis com magnitude proporcional à tensão
positiva, com direção positiva, e não com 50% correspondendo a zero.
O ponto de 0% informado corresponde a −2,2 mV em relação ao GND;
essa leitura isolada não caracteriza deriva ou incerteza do instrumento.
Não foram validadas polaridade negativa, transientes ou compatibilidade
elétrica para ligação direta da saída analógica à entrada do encoder.
Nenhuma compensação de ganho ou offset foi aplicada no aplicativo.

## Pulso automático de 40% / 500 ms

Operador confirmou funcionamento do botão e informou pico de **4,46 V** no
osciloscópio para comando de +4 V nominal. Patamar informado em seguida:
**4,0960 V**. Configuração da ponta, impedância de entrada, largura de banda
e forma da transição ainda não registradas. Não classificar o pico isolado como erro estático de ganho
ou não linearidade, nem atribuir sua causa a uma impedância sem medições.
