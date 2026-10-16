# Relatório Executivo de Análise Exploratória (EDA) — Pool v6

> **Status do Dataset:** v6 Oficial • **Total de Registros:** 91,080 linhas rotuladas  
> **Distribuição Global:** 66,772 Fake (73.31%) • 24,308 True (26.69%) • Razão: **2.75:1**

---

## 1. Visão Geral e Invariantes do Dataset

A versão 6 do corpus FakenewsBR integra um pool completo com **91,080 textos rotulados**, cobrindo **36 grupos de procedência** e múltiplos canais de disseminação.

| Métrica | Valor Medido | Observação / Implicação |
| :--- | :---: | :--- |
| **Linhas Rotuladas** | `91,080` | Base completa para treino e avaliação |
| **Proporção Fake / True** | `73.3% / 26.7%` | Desbalanceamento moderado natural de checadores de fatos |
| **Grupos Informativos** | `36,896 linhas` | Grupos com diversidade fake/true (`is_balanced_group=True`) |
| **Grupos de Rótulo Constante** | `39,373 linhas (11 grupos)` | Risco de atalho (*shortcut learning*) por procedência |
| **Linhas com Mojibake / U+FFFD** | `4` | Resíduo mínimo de decodificação limpo e auditado |

### Distribuição por Tier de Confiabilidade de Rótulo (`label_tier`)
| label_tier    |   fake |   true |
|:--------------|-------:|-------:|
| checker       |  34479 |   9868 |
| checker_match |   4057 |    109 |
| corroborated  |      0 |      9 |
| llm_local     |      0 |   3092 |
| v1            |  28236 |  11230 |

---

## 2. Análise de Comprimento e Distribuição Textual

O número de palavras (`word_len`) varia significativamente entre classes e formatos de publicação. Enquanto notícias verdadeiras tendem a seguir estruturas jornalísticas mais extensas, notícias falsas frequentemente concentram formatos mais curtos e diretos, típicos de redes sociais e mensageria.

| label   |   count |    mean |   median |      std |   p75 |   p95 |
|:--------|--------:|--------:|---------:|---------:|------:|------:|
| fake    |   66772 | 40.2581 |       16 |  93.7778 | 25    |   178 |
| true    |   24308 | 58.4249 |       18 | 132.548  | 34.25 |   243 |

![Distribuição do Tamanho dos Textos](file:////Users/aluno1/Documents/Desenvolvimento/fakenewsbr/FakenewsBR/plots/v6/01_length_distribution_by_class.png)

### Comprimento por Grupo
A análise dos grupos revela disparidades marcantes: grupos procedentes do WhatsApp (`FakeWhatsApp.BR_2018`) e checadores de boatos rápidos (`FC_BOATOS_VIRAL`) possuem medianas de tamanho substancialmente menores do que veículos de imprensa institucional.

![Tamanho dos Textos por Grupo](file:////Users/aluno1/Documents/Desenvolvimento/fakenewsbr/FakenewsBR/plots/v6/02_length_distribution_by_group.png)

---

## 3. Riqueza Vocabular e Diversidade Léxica

Avaliamos a riqueza lexical por meio do **Type-Token Ratio (TTR)** e a frequência de **Hapax Legomena** (palavras de ocorrência única).

| Subconjunto | Total Tokens | Tipos Únicos | TTR (%) | Hapax Legomena | Hapax (%) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Fake News** | `2,359,662` | `72,238` | `3.06%` | `27,111` | `37.53%` |
| **Notícias Reais** | `1,236,132` | `50,038` | `4.05%` | `19,420` | `38.81%` |

> 📌 **Achado Linguístico:** Notícias verdadeiras apresentam maior variedade lexical global devido à cobertura temática mais ampla e textos mais aprofundados. Já textos desinformativos exibem vocabulário concentrado em temas recorrentes e polarizados.

---

## 4. Bigramas Mais Discriminativos (Log-Odds Ratio com Dirichlet Prior)

A metodologia de *Monroe, Colaresi & Quinn (2008)* isola os termos cuja presença oferece maior evidência estatística em favor de uma classe, corrigindo distorções causadas por termos hiper-frequentes.

![Bigramas Discriminativos](file:////Users/aluno1/Documents/Desenvolvimento/fakenewsbr/FakenewsBR/plots/v6/04_discriminative_bigrams_log_odds.png)

* **Marcadores de FAKE:** Presença marcante de verbos de urgência, conspiração e convocação de compartilhamento ("veja video", "compartilhe urgente", "escondem de voce").
* **Marcadores de TRUE:** Termos da esfera institucional, processo penal, judiciário e declarações formais ("ministerio publico", "segundo assessoria", "tribunal justica").

---

## 5. Marcadores Estilísticos e Sensacionalismo

Comparação de intensidade estilística entre as classes:

| label   |   uppercase_word_ratio |   urgency_density |   num_exclamations |   num_questions |   sentiment_polarity |
|:--------|-----------------------:|------------------:|-------------------:|----------------:|---------------------:|
| fake    |              0.0291467 |          0.313628 |           0.298913 |        0.304005 |          -0.00337396 |
| true    |              0.0242831 |          0.117116 |           0.207298 |        0.291098 |           0.0505684  |

![Dashboard de Marcadores Estilísticos](file:////Users/aluno1/Documents/Desenvolvimento/fakenewsbr/FakenewsBR/plots/v6/05_stylistic_markers_dashboard.png)

* **Caixa Alta (Shouting):** Significativamente mais frequente em fake news (`0.03%` vs `0.02%`), denotando apelo emotivo e ênfase sensacionalista.
* **Pontuação Exclamativa:** Dispara especialmente no canal WhatsApp e redes sociais.
* **Polaridade de Sentimento:** Notícias falsas mostram viés pronunciado de negatividade, perigo e indignação.

---

## 6. Auditoria de Atalhos e Vieses (Shortcut Learning)

O pool v6 possui **11 grupos com rótulo constante (100% fake ou 100% true)** totalizando **39,373 linhas**.

| Grupo Constante | Total Linhas | Rótulo Único |
| :--- | :---: | :---: |
| `fakes` | `20,347` | `fake` |
| `FC_BOATOS` | `10,772` | `fake` |
| `true` | `2,710` | `true` |
| `FC_BOATOS_VIRAL` | `2,360` | `fake` |
| `NEWS_PODER360` | `1,338` | `true` |
| `NEWS_BRASILDEFATO` | `909` | `true` |
| `NEWS_OECO` | `468` | `true` |
| `NEWS_ECO` | `453` | `true` |
| `FC_ALETHEIA` | `9` | `fake` |
| `MuMiN-PT_raw` | `4` | `fake` |
| `FC_NEXO` | `3` | `fake` |

![Composição de Rótulo nos Grupos](file:////Users/aluno1/Documents/Desenvolvimento/fakenewsbr/FakenewsBR/plots/v6/06_group_label_composition.png)

> ⚠️ **Recomendação para Modelagem (Fine-Tuning):**  
> Se o modelo for treinado sem ponderação de grupo, ele aprenderá a reconhecer o vocabulário do veículo/canal em vez do padrão de desinformação. O uso de **DFR (Deep Feature Reweighting) cell-level com `weight_clip=25`**, conforme definido no plano da v6, é estritamente mandatário.

---

## 7. Distribuição dos Splits de Avaliação

Verificação da integridade das partições de treino, validação e teste:

![Distribuição dos Splits](file:////Users/aluno1/Documents/Desenvolvimento/fakenewsbr/FakenewsBR/plots/v6/07_splits_distribution.png)

* **`full_iid` (70/10/5/15):** Pool completo estratificado preservando proporções por grupo.
* **`ood_wa`:** Reserva todo o canal WhatsApp para teste out-of-distribution (avaliando generalização cross-channel).
* **`bal_iid`:** Subconjunto canônico restrito aos grupos informativos equilibrados.

---

*Relatório gerado automaticamente pelo pipeline EDA v6 • FakenewsBR*
