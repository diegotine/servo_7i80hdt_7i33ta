# T3D Analog Velocity — versão 0.2.7

> **DRIVER ETHERNET PRÓPRIO — USE A PLACA MESA SEM LINUXCNC OU HAL.**
>
> Comunicação direta com a Mesa 7i80HDT, sem instalar ou executar LinuxCNC.

Aplicativo para Linux que controla até quatro servomotores T3D em modo de
velocidade, usando uma placa Mesa 7i80HDT pela rede Ethernet e uma 7i33TA
conectada à porta P3. O software calcula as trajetórias de posição, acompanha
os encoders e envia referências analógicas de velocidade ao drive.

## Recursos disponíveis

- Aba individual por motor, com posição, velocidade, erro de seguimento e
  indicação do comando ENABLE.
- Movimento para uma posição definida e JOG com retenção nos dois sentidos.
- Alteração do RPM durante o JOG, inclusive ao confirmar o campo com Enter.
- Aceleração e desaceleração independentes, ajustáveis durante o movimento, campos com botões `[+][−]`
  lado a lado e unidades à direita.
- STOP com desaceleração e manutenção do ENABLE; botão ENABLE para habilitar
  ou desabilitar cada motor.
- Modo de teste de saída com posição virtual calculada e leitura real do
  encoder preservada, permitindo observar movimento manual e erro.
- Gráfico por motor com posição comandada e feedback real do encoder.
- Ajustes do motor com a placa conectada e troca de modo teste com ENABLE ligado.
- Aba TESTES com loopback digital ENA → encoder A, 100 ciclos e médias de ON/OFF.
- Loopback analógico 0/+4 V e teste manual PWM/PDM com pulso de 40%.
- Monitor de períodos em aplicativo C++ separado, com afinidade em outra CPU,
  log de estatísticas, estouros de trabalho e ciclos perdidos.
- Aba Pinout com fotografia incorporada e fundo transparente.
- Faixa analógica fixa em ±10 V e limite de velocidade padrão de 1000 RPM.
- Abas de entradas e saídas digitais das portas P1 e P2.
- Aba de diagnóstico da HDT, com identificação, contadores, estados e histórico
  de falhas; após uma falha, mantém a comunicação disponível para diagnóstico
  quando a placa responde.
- Temporização absoluta de 1 ms, métricas do ciclo e ajustes de prioridade/CPU com diagnóstico do resultado efetivo.
- Configurações por motor que podem ser salvas e carregadas.
- Interface separada em arquivos `.ui`, editáveis no Qt Designer.

## Organização e requisitos

A interface utiliza C++20 e Qt 6 Widgets. O driver Ethernet próprio e o
controlador utilizam módulos Cython, com núcleo C++ para temporização, estatísticas
e rampas assimétricas. Os fontes Python existentes permanecem como integração
durante a migração incremental.

Para compilar e executar: Linux, CMake 3.21 ou superior, compilador C++20,
Qt 6.4 ou superior, Python 3.10 ou superior com cabeçalhos e Cython 3.2 ou superior. Execute `./iniciar.sh` na pasta
do projeto. As instruções detalhadas estão em [README.md](README.md), e a
pinagem em [PINOUT.md](PINOUT.md).

Os padrões de aceleração e desaceleração são 350 e 600 RPM/s. O ciclo atual da 0.2.7 é de 1 ms.
O auxiliar de CPU pertence à interface: solicita limites de 4200 MHz mesmo com
TuneD ativo, preservando os demais ajustes do perfil. O diagnóstico identifica
a versão do núcleo. O auxiliar do driver concede somente FIFO/memória.

## Estado da versão 0.2.7

Evolução da versão 0.1 com telemetria, testes de bancada, núcleo nativo,
aceleração/desaceleração independentes e monitor separado. As medições de
loopback e o ajuste da rede estão documentados em `medicoes/`. A validação do
conjunto completo com cabo, drive, motor e encoder é a próxima etapa.

Há testes automatizados do driver, controlador e comunicação com placa
simulada, além da verificação de abertura e estabilidade do layout da interface.
Esses testes não substituem as medições de saída, a conferência de encoder,
a calibração e a sintonia com o motor real.

A versão não inclui homing automático, recuperação de posição absoluta,
leitura Modbus de alarmes ou controle de freio. A indicação de ENABLE representa
o comando enviado à Mesa, sem confirmação elétrica do estado do drive.

## Descrição curta para o repositório

Controle de até quatro servomotores T3D via Mesa 7i80HDT e 7i33TA, com interface
Qt, driver Ethernet próprio e uso da placa sem LinuxCNC ou HAL. Inclui JOG,
trajetórias de posição, teste de saída e diagnóstico.

Backend, driver Ethernet, controlador, loopback e temporização são compilados
com Cython. O núcleo C++ executa temporização, estatísticas e planejamento
de rampas; o estado numérico do controlador usa campos C. Consulte
[RELEASE_0.2.7.md](RELEASE_0.2.7.md) para mudanças e validação desta publicação.
