# Histórico de versões

## 0.2.4 — conversão Cython

- Versão incrementada antes da conversão; período de 2 ms preservado.
- Referência física 0.2.3 com FIFO e memória bloqueada salva para comparação.
- Backend, servo, driver Ethernet, loopback e temporização compilados em extensões Cython.
- Estado numérico de Axis/Trajectory em campos C; encoder mantém contador inteiro sem limite de 64 bits.
- Inicialização verifica que os cinco módulos carregados são extensões; diagnóstico e JSON identificam Cython.
- Equivalência matemática e permissões verificadas sem placa; medição física desta versão pendente.

## 0.2.3 — em desenvolvimento

- Corrigido bloqueio de memória: ambiente neutro UTF-8 no backend evita o arquivo de idiomas de 223 MiB.
- Checagem de permissões carrega módulos reais e uma thread; reproduziu a falha anterior e confirmou o bloqueio após a correção.
- Regra restrita no sudoers para o auxiliar, que abandona root antes de executar o driver.

- Ciclo nominal reduzido de 5 ms para 2 ms (500 Hz), mantendo limite de falha de 20 ms e watchdog de 100 ms.
- Diagnóstico conta execuções de leitura/cálculo/escrita acima do período nominal.
- Indicadores e exportação JSON usam o período real configurado.
- Auxiliar opcional concede limites ao backend; verificação real confirmou FIFO 10 e bloqueio da memória atual, sem executar a placa.
- Novo atalho v0.2.3 preserva os anteriores.
- Medição física pendente; sem execução de placa simulada nesta etapa.

## 0.2.2 — referência com otimizações

- Temporização absoluta nativa, sem acumular atrasos ou executar ciclos de compensação.
- Afinidade de CPU, tentativa SCHED_FIFO e bloqueio de memória atual, com resultado visível no diagnóstico.
- Coleta automática de referências cíclicas Python suspensa no ciclo de controle.
- Métricas de ciclo, despertar, leitura, cálculo e escrita; inclusão nos JSONs de loopback.
- Referência 0.2.0 preservada para comparação real; limite de 20 ms, watchdog e PID mantidos.
- Loopback analógico medido: ON 4,982 ms e OFF 4,972 ms (executável ainda identificado como 0.2.1 na captura).
- Afinidade confirmada em CPU 5; prioridade RT e bloqueio de memória recusados pelo sistema nessa medição.

## 0.2.1 — preparação

- Incremento anterior às otimizações, registrado no commit 604bcb6.
- A versão com otimizações foi renumerada para 0.2.2 por orientação do operador.

## 0.2.0 — referência de bancada, 11/10/2026

- Gráfico de comando e feedback real do encoder por motor.
- Modo teste alternável com ENABLE ligado, preservando a posição virtual.
- Ajustes do motor aplicáveis com a placa conectada.
- Faixa analógica fixa em ±10 V e limite padrão de 3000 RPM.
- Aba TESTES com loopback digital ENA → encoder A, médias de ON/OFF e dispersão.
- Loopback analógico 0/+4 V com retorno pela entrada A e resultados identificados por modo.
- Campo de teste manual de magnitude PWM/PDM (0–100%), aplicar e zerar/desligar.
- Pulso automático de 40% por 500 ms para osciloscópio, independente do retorno A.
- Loopbacks digital e analógico medidos em bancada; validação com motor ainda pendente.

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
