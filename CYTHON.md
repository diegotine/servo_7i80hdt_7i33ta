# Conversão Cython — 0.2.4

O período permanece em **2 ms (500 Hz)**. O CMake compila `backend`, `servo`,
`mesa7i80hdt`, `loopback` e `timing` em extensões `.so` para a ABI do Python
selecionado. As fontes oficiais continuam em `driver/*.py`; `servo.pxd`
acrescenta os tipos nativos. C gerado e HTML de anotação ficam em
`build/native/`, e as extensões em `build/driver/`. Não editar o C gerado.

`Axis` e `Trajectory` têm campos numéricos C `double`; flags usam booleanos C.
Métodos cíclicos recebem `dt` como `double`. O contador acumulado do encoder
continua inteiro Python para preservar seu alcance ilimitado. Configurações
continuam dataclasses, mantendo validações e o formato JSON.

A interface Qt e seus `.ui` continuam separados e editáveis. O programa exige
os cinco módulos compilados antes de acessar a placa; não troca silenciosamente
para fontes interpretadas. O auxiliar/sudoers existente continua compatível:
a entrada `backend.py` delega ao módulo compilado antes de abrir a comunicação.
O diagnóstico mostra **Controle Cython**, e o JSON informa `native_servo=true`
e os caminhos reais dos módulos em `runtime.native_modules`.

## Compilar

Requer Python com cabeçalhos de desenvolvimento, Cython ≥3.2, compiladores C/C++,
CMake e Qt6. No Fedora:

```sh
sudo dnf install python3-cython python3-devel
./iniciar.sh
```

Cython não é necessário para importar extensões já compiladas, mas é necessário
para reconstruir o projeto. Recompilar ao trocar a ABI do Python. A compilação
usa otimizações de Release, sem `fast-math`, sem desligar verificações de
limites e sem tornar exceções de controle silenciosas.

## Verificação sem placa

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=build/driver python3 tests/test_native_compat.py -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=build/driver python3 -m unittest discover -s tests -p test_timing.py -v
sudo -n -- /usr/local/libexec/t3d-analog-runtime-$(id -u) --check
```

Passaram seis verificações de equivalência entre fontes e extensões: carga dos
cinco módulos, bytes/validação de pacotes LBP16, encoder com wrap e contador acima de 64 bits, amostras de trajetória,
cálculo isolado nos modos de operação e falhas de prazo. Passaram também sete
verificações de temporização. Essas verificações não abrem UDP e não simulam a
placa nem uma planta. A checagem real de permissões confirmou FIFO 10, memória
atual bloqueada, UID do usuário e ausência de capabilities efetivas.

A compilação limpa foi conferida em `build/native-verify`. A anotação e o C gerado
confirmam o armazenamento nativo do estado. Avisos extras do Cython foram
inspecionados: símbolos internos `genexpr` e suposta ausência de atribuição de
`config`/`reply` após blocos `with`. As atribuições antecedem o uso; falhas ao
abrir/ler propagam exceção e não alcançam esse uso. Não se alterou esse fluxo.

Foi tentada compilação ASan/UBSan em diretório separado, mas a ligação falhou
porque as bibliotecas de runtime `libasan.so.8.0.0` e `libubsan.so.1.0.0` não
estão instaladas. TSan também não foi executado: seu runtime não está instalado
e o CPython do sistema não foi instrumentado. `clang-tidy` e `cppcheck` não estão
disponíveis. Não há alegação de validação por esses analisadores.

## Comparação física

Referência: `medicoes/loopback-analogico-0.2.3-mlock-2026-10-11.json`.
Repetir o loopback analógico com a mesma ligação e comparar intervalo,
trabalho, desvio, P95, máximos e horários pulados. A latência/desvio da 0.2.4
será confirmada pelo operador; não foi estimada com placa simulada.

Compilar reduz interpretação e operações com objetos em parte da malha.
CPython, GIL, sockets, filas e telemetria ainda participam da execução. Isso
não elimina jitter de kernel, Ethernet ou agendamento, nem garante tempo real
rígido. A GUI não muda ganhos PID automaticamente; watchdog, limites, pinagem,
faixa ±10 V e amplitude do loopback permanecem os mesmos.

Referências oficiais: [modo Python e tipos estáticos do Cython](https://cython.readthedocs.io/en/stable/src/tutorial/pure.html),
[compilação e diretivas](https://cython.readthedocs.io/en/stable/src/userguide/source_files_and_compilation.html).
