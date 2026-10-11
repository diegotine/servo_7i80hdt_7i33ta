# Histórico de versões

## 0.2.7 — publicação e monitor de períodos

- Correção posterior à publicação: sair do modo teste preserva a posição acumulada como origem local do encoder; o erro passa a ser o da malha real e acompanha movimento manual mesmo desabilitado. Limites locais acompanham a origem sem ampliar o curso físico. Nenhum salto de referência é enviado ao PID.

- Reúne as melhorias de controle, telemetria, núcleo nativo e bancada desde a publicação 0.1.0.
- Mantém a grade absoluta de 1 ms, aceleração de 350 RPM/s e desaceleração de 600 RPM/s.
- Monitor C++/Qt em processo separado e outra CPU, com log das estatísticas existentes, estouros de trabalho e ciclos perdidos.
- Telemetria encaminhada pela interface por socket local sem bloqueio; sem gravação em disco na malha.
- Documentação e capturas atualizadas; firmware da HDT preservado.
- Compilação Release, testes de interface/IPC e testes matemáticos nativos/temporização aprovados; validação com motor e drive pendente.

## 0.2.6 — política de CPU da interface

- Atualização a pedido do operador: período nominal de 1 ms (1000 Hz); limites de falha, watchdog e heartbeat preservados. Medição física pendente.

- Versão incrementada antes da separação do auxiliar de clock da interface e do auxiliar de permissões do driver.
- Interface controla `t3d_cpu_policy`, sem inicializar o driver; fechamento da interface restaura o ajuste.
- Binários e auxiliares instalados por versão; 0.2.5 preservada para comparação.

## 0.2.5 — otimização nativa

- Com TuneD ativo, solicita mínimo/máximo de 4200 MHz na CPU dedicada e restaura ao fechar, preservando os demais ajustes do perfil.

- Aba Pinout com a fotografia da 7i33TA centralizada horizontalmente; fundo externo transparente em PNG. A conversão JPG inicial também foi preservada.

- Versão incrementada antes das otimizações; período de 2 ms mantido.
- Referência física 0.2.4 salva antes das mudanças.
- Núcleo C++ para temporização absoluta, estatísticas e rampas assimétricas.
- Aceleração e desaceleração separadas; padrões 350 e 600 RPM/s, limite/JOG 1000 RPM.
- Helper aplica governador e ajustes de CPU inspirados no TuneD ao abrir e restaura ao fechar.
- Solicitação de 4200 MHz condicionada ao suporte real do driver; diagnóstico explícito.
- Validação matemática, compatibilidade e interface sem acionar ou simular a placa.

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
