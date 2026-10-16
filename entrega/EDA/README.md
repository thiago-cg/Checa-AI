# Relatórios e Análise Exploratória de Dados (EDA) — FakenewsBR v6

Este diretório contém os relatórios gerados a partir da análise exploratória de dados (**EDA**) do **Pool v6** (91.080 textos rotulados) do projeto FakenewsBR.

O relatório HTML gerado é **100% autocontido**: todas as visualizações, gráficos e estilos CSS são embutidos diretamente no arquivo (via *Data URI Base64*), permitindo que ele seja compartilhado por e-mail, Slack ou arquivado sem risco de quebra de caminhos de imagens.

---

## 🚀 Como Visualizar o Relatório HTML

### 1. Abertura Direta no Navegador (Recomendado)

Você pode abrir o arquivo `eda_v6_report.html` diretamente com o navegador padrão do seu sistema operacional:

* **No macOS:**
  ```bash
  open entrega/EDA/eda_v6_report.html
  ```

* **No Linux:**
  ```bash
  xdg-open entrega/EDA/eda_v6_report.html
  ```

* **No Windows (PowerShell / Prompt):**
  ```powershell
  start entrega/EDA/eda_v6_report.html
  ```

---

### 2. Via Servidor Local HTTP

Caso prefira visualizar via servidor web local:

```bash
# Na raiz do repositório CrossCheckBR:
python3 -m http.server 8000
```

Em seguida, acesse no navegador:
👉 **[http://localhost:8000/entrega/EDA/eda_v6_report.html](http://localhost:8000/entrega/EDA/eda_v6_report.html)**

---

## 🛠️ Como Executar / Atualizar a Análise

### Pré-requisitos
Certifique-se de ter instalado os pacotes necessários:
```bash
pip install pandas pyarrow numpy matplotlib seaborn scikit-learn markdown
```

---

### Opção A: Executar a Pipeline Completa da EDA v6
Executa a leitura dos dados parquet, cálculos estatísticos e léxicos, gera os gráficos em `plots/v6/`, salva o Markdown e **compila o HTML automaticamente**:

```bash
python investigation/eda_v6.py
```

#### Parâmetros Opcionais da CLI:
```bash
python investigation/eda_v6.py \
  --pool-path pipeline/prepare/processed/v6_pool.parquet \
  --splits-path pipeline/prepare/processed/v6_splits.parquet \
  --plots-dir plots/v6 \
  --reports-dir reports \
  --no-html   # Use caso queira apenas os gráficos e o Markdown, sem o HTML
```

---

### Opção B: Recompilar Apenas o Relatório HTML
Se você editou o arquivo `reports/eda_v6_report.md` ou deseja converter qualquer outro documento Markdown com gráficos embutidos em Base64:

```bash
python investigation/generate_html_report.py \
  --input reports/eda_v6_report.md \
  --output reports/eda_v6_report.html \
  --title "FakenewsBR v6 • Relatório Executivo de EDA"
```

---

## 📁 Estrutura dos Arquivos Gerados

```text
FakenewsBR/
├── plots/
│   └── v6/                                 # Gráficos em alta resolução (200 DPI)
│       ├── 01_length_distribution_by_class.png
│       ├── 02_length_distribution_by_group.png
│       ├── 03_temporal_and_channel_distribution.png
│       ├── 04_discriminative_bigrams_log_odds.png
│       ├── 05_stylistic_markers_dashboard.png
│       ├── 06_group_label_composition.png
│       └── 07_splits_distribution.png
├── reports/
│   ├── README.md                           # Este guia explicativo
│   ├── eda_v6_report.html                  # Relatório HTML autocontido (~1.3 MB)
│   ├── eda_v6_report.md                    # Relatório síntese em Markdown
│   └── eda_v6_stats.json                   # Métricas e estatísticas em JSON
└── investigation/
    ├── eda_v6.py                           # Script de análise e geração da EDA v6
    └── generate_html_report.py             # Compilador portátil Markdown -> HTML
```

---

## 📊 Conteúdo Coberto no Relatório

1. **Invariantes e Equilíbrio de Classes:** Distribuição de 91.080 textos (73,31% fake vs 26,69% true, razão 2,75:1).
2. **Comprimento Textual:** Boxplots e distribuições KDE em escala logarítmica por classe e por grupo de procedência.
3. **Diversidade Léxica:** Medições de *Type-Token Ratio* (TTR) e frequência de *Hapax Legomena*.
4. **N-Grams Discriminativos:** Termos identificados via *Log-Odds Ratio com Dirichlet Prior* (Monroe et al.).
5. **Estilo e Sensacionalismo:** Comparativo de proporção de caixa alta (*shouting*), pontuação exclamativa, léxico de urgência e polaridade de sentimentos.
6. **Auditoria de Atalhos (*Shortcuts*):** Mapeamento dos 11 grupos constantes (39.373 linhas) e 8 informativos (36.896 linhas).
7. **Integridade das Partições:** Distribuições dos splits `full_iid`, `ood_wa` e `bal_iid`.
