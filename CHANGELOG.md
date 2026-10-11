# Histórico de versões

## 0.2.1 — em desenvolvimento

- Otimizações de temporização e diagnóstico de latência em implementação.

## 0.2.0 — referência de bancada, 11/10/2026

- Gráfico de comando e feedback real do encoder por motor.
- Modo teste alternável com ENABLE ligado, preservando a posição virtual.
- Ajustes do motor aplicáveis com a placa conectada.
- Faixa analógica fixa em ±10 V e limite padrão de 3000 RPM.
- Aba TESTES com loopback digital ENA → encoder A, médias de ON/OFF e dispersão.
- Loopback analógico 0/+4 V com retorno pela entrada A e resultados identificados por modo.
- Campo de teste manual de magnitude PWM/PDM (0–100%), aplicar e zerar/desligar.
- Pulso automático de 40% por 500 ms para osciloscópio, independente do retorno A.
- Validação física de bancada pendente.

## 0.1.0 — 2026-10-11

Primeira versão para testes de bancada do controle de quatro servomotores T3D
com Mesa 7i80HDT e 7i33TA.

- Driver Ethernet próprio, com uso da placa sem LinuxCNC ou HAL.
- Interface Qt com abas individuais dos motores, I/O e diagnóstico da HDT.
- Trajetórias de posição, JOG com retenção e ajuste de RPM durante o movimento.
- Aceleração máxima ajustável e STOP que mantém ENABLE.
- Teste de saída com posição virtual e leitura real do encoder preservada.
- Diagnóstico após falhas e rearme explícito pelo botão ENABLE.
- Interface editável no Qt Designer, separada do código de controle.
- Documentação, pinagem, diagramas e capturas da interface.

Validação: compilação concluída, 52 testes Python e verificação da interface Qt
aprovados. A calibração, a sintonia e a validação prática com o conjunto completo
permanecem pendentes. Esta versão distribui o código-fonte; a compilação e os
requisitos estão descritos no README.
