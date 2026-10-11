# Loopback: latência de ENABLE até a entrada do encoder

## Ligação na 7i33TA

Use os **bornes da 7i33TA**, não os pinos /ENABLE do flat P3. ENA é uma
saída CMOS de 5 V ativa em nível alto; /ENABLE do flat tem polaridade oposta.
No modo digital, não use DRV (saída analógica ±10 V). Não use +5 V de alimentação ou sinais de 24 V.

Com a alimentação desligada para montar o fio, retire as conexões do drive
e do encoder externo do canal escolhido. O teste alterna ENABLE 100 vezes;
essa saída não deve estar ligada ao SON de um drive durante o ensaio.
Coloque o jumper do canal em **TTL (posição DOWN)**. Não use esta ligação
de um fio com o jumper em RS-422.

| Motor no app | Canal na 7i33TA | Fio de ENA para A | Jumper TTL |
|---|---|---|---|
| Motor 1 | CH0 | TB1 pino 12 → TB1 pino 1 | W4 |
| Motor 2 | CH1 | TB2 pino 12 → TB2 pino 1 | W3 |
| Motor 3 | CH2 | TB1 pino 24 → TB1 pino 13 | W2 |
| Motor 4 | CH3 | TB2 pino 24 → TB2 pino 13 | W1 |

TB1 é o bloco interno; TB2 é o bloco externo. Respeite a identificação dos
bornes na placa. Os sinais compartilham o GND da própria 7i33TA. O ensaio
mede somente o nível de A; não exige fios adicionais em B ou índice.
As entradas invertidas /A e /B não são usadas neste teste TTL.

Fontes: manual Mesa 7i33/7i33TA V1.9, PDF 5 / impressa 2 (jumpers),
PDF 10–11 / impressas 7–8 (bornes), PDF 12 / impressa 9 (entrada TTL
inversora) e PDF 13 / impressa 10 (ENA). A pinagem P3 é validada pelo driver.

## Executar

1. Monte a ligação acima, alimente as placas e conecte o aplicativo.
2. Deixe os quatro motores desabilitados e selecione o canal na aba TESTES.
3. Clique em **Loopback**. O teste usa a conexão existente, sem outro cliente.
4. A entrada precisa confirmar OFF estável por 50 ms. Depois o programa
   alterna ON e OFF, esperando cada retorno e uma pausa de 50 ms.
5. Aguarde 100 ciclos, aproximadamente 12 segundos. Os campos mostram as
   médias de ON e OFF em milissegundos. O resumo inclui mínimo, máximo,
   percentil 95 e desvio padrão, separados para as duas bordas. O aplicativo
   salva as 100 amostras de cada borda em JSON na pasta de dados do usuário,
   dentro de `loopback/`, e mostra o caminho do arquivo no resumo.
6. **Cancelar loopback** interrompe o ensaio e solicita ENABLE desligado.
   Ao concluir, a última borda OFF deve ter sido recebida. Saídas analógicas
   permanecem em zero no teste digital e não há habilitação automática de motor após o teste.

Durante o ensaio, comandos de movimento e ajustes são recusados. Os contadores
do encoder continuam sendo lidos, sem zerar seus registradores; alternar A pode
produzir contagens pequenas que vão e voltam. O critério do teste é o nível
elétrico de A lido pelo GPIO da FPGA, não a variação do contador. O software
considera a inversão do condicionador TTL da 7i33TA.

Se faltar uma borda por 500 ms, houver retorno instável, perda de comunicação
ou prazo de controle excedido, o teste é interrompido. Um resultado incompleto
não é apresentado como média válida de 100 ciclos. Falhas de comunicação
seguem o diagnóstico e watchdog já existentes, sem repetição automática.

## O que o tempo significa para o PID

O instante inicial é registrado com relógio monotônico imediatamente antes do
envio do pacote UDP que muda ENABLE. O marco final é registrado ao receber
o pacote de leitura em que o novo nível de A foi observado. A janela do
aplicativo não cronometra o ensaio; ela apenas recebe os resultados.

O valor inclui envio pela rede, processamento da placa, saída ENA, filtro TTL,
espera pela próxima leitura, retorno pela rede e escalonamento do computador.
O ciclo nominal atual de leitura da 0.2.6 é 1 ms: um cronômetro com resolução de nanossegundos
não torna a detecção do nível igualmente precisa. Não é possível separar
atrasos de ida e volta nem medir apenas o tempo da FPGA com este ensaio.

O loopback digital também não inclui o filtro da saída analógica, a resposta
do servodrive, o motor e a mecânica. Portanto, ajuda a avaliar o orçamento de
atraso e sua variação para a sintonia do PID, mas não fornece ganhos PID nem
um atraso de planta completo. Use também os maiores tempos e a dispersão,
não só a média. Para observar atrasos elétricos abaixo do ciclo de leitura,
compare ENA e A com o osciloscópio. O aplicativo não modifica o PID com o resultado.

## Loopback analógico — 0 V / +4 V

Selecione **Analógico • 0 / +4 V** na aba TESTES. O ensaio usa a mesma
entrada A e alterna o comando analógico entre 0 V e +4 V por 100 ciclos.
O canal permanece habilitado durante a medição, inclusive em 0 V; ao concluir,
cancelar ou falhar, solicita zero e retira ENABLE. Não comanda tensões negativas.
O drive e o encoder externo devem estar desconectados do canal.

### Conferir com osciloscópio antes do fio de retorno

Para Motor 1, ponta de sinal em TB1 pino 10 (DRV0) e referência em TB1
pino 9 (GND analógico). Mantenha A desconectada da saída. Use captura única
com disparo na subida, abrangendo pelo menos 600 ms, para observar também
o retorno a zero. Clique **Pulso 40% / 500 ms**: esse botão aplica +4 V nominal
por aproximadamente 500 ms, depois zera e retira ENABLE, sem consultar a
entrada A e sem exigir Aplicar no campo manual. Não calcula latência.

O botão Loopback é o ensaio com retorno: exige A em zero estável por 50 ms
antes do primeiro pulso. Com A aberta e flutuando, pode não aplicar o pulso.
Essa condição não se aplica ao botão de pulso para osciloscópio.

Confira tensão máxima, mínima e transientes; não interprete o comando nominal
como garantia de compatibilidade elétrica. A medição manual anterior indicou
5,0671 V em 50% e −2,2 mV em zero.

| Motor | Saída analógica | Entrada de retorno | Jumper TTL |
|---|---|---|---|
| 1 | TB1 pino 10 — DRV0 | TB1 pino 1 — A0 | W4 |
| 2 | TB2 pino 10 — DRV1 | TB2 pino 1 — A1 | W3 |
| 3 | TB1 pino 22 — DRV2 | TB1 pino 13 — A2 | W2 |
| 4 | TB2 pino 22 — DRV3 | TB2 pino 13 — A3 | W1 |

**Compatibilidade elétrica:** o manual identifica DRV como saída ±10 V e A
como entrada TTL; não garante tolerância de A à faixa analógica. Uma interface
comparadora com saída TTL oferece o condicionamento apropriado. O operador
informou que pretende ligação direta: a restrição do comando a 0/+4 V não é
uma proteção elétrica contra sobretensão, tolerância ou transientes. Confira
os níveis reais com osciloscópio antes de conectar à entrada; não use comandos
de movimento nem troque para o controle normal com esse fio instalado.

O resultado é o tempo até o cruzamento do limiar digital, incluindo o filtro
analógico, a entrada TTL, rede e ciclo de leitura de 1 ms. Não mede o tempo
até a tensão se estabilizar em +4 V. No modo sign-magnitude usado aqui,
+4 V corresponde a 40% de magnitude; zero corresponde a magnitude zero.
A exportação JSON identifica o modo analógico separadamente do digital.

## Medir a relação magnitude / tensão antes do loopback analógico

Retire o fio de retorno ao encoder e desconecte o drive. Selecione o motor,
informe a magnitude em **Teste manual PWM/PDM** e clique **Aplicar**.
O comando é manual, positivo e constante; alterar o campo só aplica após clicar
novamente. **Zerar / desligar** comanda zero e retira ENABLE.

Para Motor 1, meça com multímetro entre **TB1 pino 10 (DRV0, positivo)** e
**TB1 pino 9 (GND analógico, negativo)**. Não use A como retorno do multímetro.
Valores nominais: 0% → 0 V, 25% → +2,5 V, 50% → +5 V, 75% → +7,5 V,
100% → +10 V. São referências calculadas, não leituras da placa.
A placa permanece no PDM de 6 MHz já configurado; o campo altera a magnitude,
não a frequência nem o modo de modulação. Os demais canais ficam desabilitados.
Movimentos e loopback são recusados enquanto o teste manual está ativo.
Watchdog e verificação de atraso continuam ativos. Ao fechar/desconectar ou
falhar, segue o desligamento da sessão; perda de rede depende do watchdog.
