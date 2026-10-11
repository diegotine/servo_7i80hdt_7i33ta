# Intel I219-LM: ajuste de latência para a rede Mesa

Data: 11/10/2026, America/Sao_Paulo.

## Diagnóstico

- Computador: Dell OptiPlex SFF 7010, BIOS 1.38.0.
- Ethernet: Intel Ethernet Connection (17) I219-LM, PCI `8086:1a1c`, interface `enp0s31f6`.
- Driver correto já carregado: `e1000e`, fornecido e assinado pelo Fedora.
- Kernel em execução: `7.2.8-200.fc44.x86_64`, PREEMPT_DYNAMIC, HZ=1000. O arquivo de configuração confirma `# CONFIG_PREEMPT_RT is not set`. Este teste não ocorreu em kernel RT.
- Perfil Ethernet: `lan-cnc`, UUID `63946251-0568-4967-8f9d-bbe8fe696286`, IP `192.168.1.250/24`. A placa Mesa responde em `192.168.1.121`.
- Internet pelo Wi-Fi `wlp2s0`; o ajuste abaixo afeta somente o cabo dedicado à Mesa.
- Link de 100 Mb/s full duplex, coerente com a capacidade máxima anunciada pelo parceiro. Sem erros RX/TX, CRC ou timeout de transmissão nas leituras.
- EEE habilitado, mas inativo: o parceiro não anunciou EEE. Runtime PM já estava em `on`, com dispositivo ativo.
- A afinidade da IRQ Ethernet já estava no CPU 2. O TuneD já usava o perfil local `mesa-performance-sem-turbo`.

## Pesquisa e decisão

Um relato original no fórum LinuxCNC identifica uma I219-LM, driver `e1000e` e kernel `6.4.0-rt6-linuxcnc`, e recomenda desativar a moderação de interrupções com `ethtool -C <interface> rx-usecs 0`. O manual oficial `hm2_eth` também recomenda `hardware-irq-coalesce-rx-usecs 0` na interface dedicada às placas Mesa. Esse ajuste é do driver de rede e também pode ser usado pelo aplicativo próprio T3D, sem instalar LinuxCNC.

A documentação do kernel explica o compromisso: remover a moderação reduz a espera dos pacotes pequenos, mas aumenta a frequência de interrupções e pode aumentar o uso de CPU. No `e1000e`, os valores 0, 1, 3 e 4 de `rx-usecs` representam modos especiais; o valor original 3 era o modo dinâmico conservador, e não um atraso literal de 3 microssegundos.

Não foram reproduzidas alterações de BIOS, isolamento de CPUs ou troca de kernel sugeridas para outras máquinas. Não havia evidência de travamento do adaptador que justificasse desativar todos os offloads. EEE não estava ativo. Esses ajustes não são equivalentes à correção de moderação de interrupções medida aqui.

## Alteração aplicada

Persistência no perfil NetworkManager:

```sh
nmcli connection modify uuid 63946251-0568-4967-8f9d-bbe8fe696286 ethtool.coalesce-rx-usecs 0
```

O NetworkManager recusou reaplicar a seção `ethtool` à conexão ativa. A alteração foi então aplicada diretamente, com autenticação administrativa pelo mecanismo do sistema:

```sh
pkexec --disable-internal-agent /usr/bin/ethtool -C enp0s31f6 rx-usecs 0
```

O comando concluiu com sucesso e a leitura posterior confirmou `rx-usecs: 0`. O perfil salvo reaplica a opção nas futuras ativações, inclusive após reiniciar. Não foi necessário reiniciar, descarregar o driver ou desconectar a interface. O contador `carrier_changes` permaneceu em 2 e as rotas permaneceram idênticas.

## Medição antes e depois

Comando idêntico nas duas fases, com 100 pacotes ICMP em aproximadamente 10,3 segundos por fase:

```sh
LC_ALL=C ping -n -I enp0s31f6 -c 100 -i 0.1 -W 1 192.168.1.121
```

| Medida | Antes: modo 3 | Depois: modo 0 |
|---|---:|---:|
| RTT médio | 0,327 ms | 0,144 ms |
| RTT mediano | 0,325 ms | 0,145 ms |
| RTT p95 | 0,345 ms | 0,163 ms |
| RTT p99 | 0,361 ms | 0,165 ms |
| RTT máximo observado | 0,367 ms | 0,168 ms |
| Desvio informado pelo ping | 0,011 ms | 0,012 ms |
| Perda | 0/100 | 0/100 |
| Interrupções da NIC por segundo, aproximadamente | 1.501 | 2.015 |
| CPU ativa agregada do sistema | 12,87% | 15,27% |
| Espera de I/O em `/proc/stat` | 0,16% | 0,27% |
| Tempo agregado em hard IRQ | 0,31% | 0,34% |
| Tempo agregado em soft IRQ | 0,29% | 0,27% |

O RTT médio caiu aproximadamente 56% nesta comparação. Os arquivos brutos `ping-before.txt` e `ping-after.txt` estão nesta pasta; também foram preservados os perfis, contadores da NIC, interrupções, `/proc/stat`, tempo de observação e rotas.

As amostras de CPU incluem todos os processos da sessão, com carga variável; a diferença não isola o custo do driver. A frequência maior de interrupções é compatível com a retirada da moderação. O teste comprova uma redução observada do RTT, sem comprovar melhora de desempenho geral, jitter de escalonamento ou garantia de tempo real. Não foi executado teste de movimento, acionamento de motores ou benchmark que saturasse a conexão.

Em uma medição exploratória anterior, separada desse teste, o Wi-Fi apresentou RTT médio de 68,924 ms ao roteador. Isso pertence a outro caminho de rede; suas configurações não foram alteradas.

## Reverter

Para remover a opção persistente e restaurar o modo original no driver ativo, sem reiniciar o link:

```sh
nmcli connection modify uuid 63946251-0568-4967-8f9d-bbe8fe696286 ethtool.coalesce-rx-usecs ""
pkexec --disable-internal-agent /usr/bin/ethtool -C enp0s31f6 rx-usecs 3
ethtool -c enp0s31f6
```

O segundo comando exige autenticação administrativa. Alternativa: `sudo /usr/bin/ethtool -C enp0s31f6 rx-usecs 3`. Remover somente a opção persistente não restaura imediatamente o valor ativo.

## Fontes

- [Relato original: I219-LM com kernel RT e recomendação de rx-usecs=0](https://forum.linuxcnc.org/42-deutsch/49646-neue-hardware-und-schlechter-latency-test?start=10).
- [Manual oficial LinuxCNC: hm2_eth, configuração de interface e moderação de interrupções](https://linuxcnc.org/docs/stable/html/man/man9/hm2_eth.9.html).
- [Documentação oficial do kernel: e1000e e InterruptThrottleRate](https://docs.kernel.org/networking/device_drivers/ethernet/intel/e1000e.html).
- [Intel: I219 usa e1000e; manutenção atual ocorre no driver do kernel](https://www.intel.com/content/www/us/en/support/articles/000005480/ethernet-products.html).
- [Código oficial do driver: leitura e aplicação da moderação sem reinicializar o adaptador](https://github.com/torvalds/linux/blob/master/drivers/net/ethernet/intel/e1000e/ethtool.c).
