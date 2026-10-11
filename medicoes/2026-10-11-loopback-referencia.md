# Referência antes das otimizações — 0.2.0

100 ciclos por ensaio, Motor 1, mesma sessão Ethernet via P3 da HDT.
Valores exibidos nas capturas fornecidas pelo operador em 11/10/2026.

| Medida | Digital ENA → A | Analógico DRV → A, 0/+4 V |
|---|---:|---:|
| ON médio | 4,933 ms | 4,971 ms |
| ON mínimo | 4,748 ms | 4,737 ms |
| ON máximo | 5,040 ms | 5,180 ms |
| ON P95 | 5,031 ms | 5,073 ms |
| ON desvio padrão | 0,050 ms | 0,062 ms |
| OFF médio | 4,940 ms | 4,969 ms |
| OFF mínimo | 4,795 ms | 4,858 ms |
| OFF máximo | 5,107 ms | 5,102 ms |
| OFF P95 | 5,013 ms | 5,063 ms |
| OFF desvio padrão | 0,048 ms | 0,049 ms |

Originais com todas as amostras:
[digital](loopback-digital-0.2.0.json) e
[analógico](loopback-analogico-0.2.0.json).
Capturas em `screenshots/loopback-*-bancada-2026-10-11.png`.

O período nominal de leitura é 5 ms e influencia os dois resultados.
Essas médias não representam um atraso isolado da placa e não são adicionadas
ao PID. A medição de comparação da 0.2.1 ainda está pendente.
