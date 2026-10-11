# Stored data checked against SCB's published figures

Produced by `python -m ingest.verify_against_scb` (also run by the monthly ingest workflow). SCB's releases use base 2015=100 and FPIBOM uses 1968=100, so percentage changes are compared.

| check (flerbostadshus) | our rows (FPIBOM, 1968=100) | our change | SCB published | match |
|---|---|---|---|---|
| Feb → Mar 2022 | 1545.50 → 1568.00 | 1.5 % | [1.5 %](https://www.scb.se/hitta-statistik/statistik-efter-amne/priser-och-ekonomiska-tendenser/priser/byggkostnadsindex-bki/pong/statistiknyhet/byggkostnadsindex-for-byggnader-mars-2022/) | yes |
| Mar 2021 → Mar 2022 | 1430.90 → 1568.00 | 9.6 % | [9.6 %](https://www.scb.se/hitta-statistik/statistik-efter-amne/priser-och-ekonomiska-tendenser/priser/byggkostnadsindex-bki/pong/statistiknyhet/byggkostnadsindex-for-byggnader-mars-2022/) | yes |
| Nov → Dec 2022 | 1737.70 → 1744.80 | 0.4 % | [0.4 %](https://www.scb.se/hitta-statistik/statistik-efter-amne/priser-och-ekonomiska-tendenser/priser/byggkostnadsindex-bki/pong/statistiknyhet/byggkostnadsindex-for-byggnader-december-2022/) | yes |
| Dec 2021 → Dec 2022 | 1508.90 → 1744.80 | 15.6 % | [15.6 %](https://www.scb.se/hitta-statistik/statistik-efter-amne/priser-och-ekonomiska-tendenser/priser/byggkostnadsindex-bki/pong/statistiknyhet/byggkostnadsindex-for-byggnader-december-2022/) | yes |
| Jul → Aug 2026 | 1922.10 → 1934.20 | 0.6 % | [0.6 %](https://www.scb.se/hitta-statistik/statistik-efter-amne/priser-och-ekonomiska-tendenser/priser/byggkostnadsindex-bki/pong/statistiknyhet/byggkostnadsindex-for-byggnader-august-2026/) | yes |
| Transport, fuel, electricity: Mar 2021 → Mar 2022 | 2194.50 → 2780.80 | 26.7 % | [26.7 %](https://www.scb.se/hitta-statistik/statistik-efter-amne/priser-och-ekonomiska-tendenser/priser/byggkostnadsindex-bki/pong/statistiknyhet/byggkostnadsindex-for-byggnader-mars-2022/) | yes |

6 of 6 match.
