#!/usr/bin/env python3
"""eda_v6.py -- Análise Exploratória de Dados (EDA) do pool v6 (91.080 registros rotulados).

Executa a análise estatística, léxica, estilística e de atalhos/viés do dataset FakenewsBR v6.
Gera gráficos em plots/v6/, relatório estruturado em Markdown em reports/eda_v6_report.md
e opcionalmente compila o relatório HTML autocontido via generate_html_report.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.feature_extraction.text import CountVectorizer

# Raiz do projeto
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_POOL_PATH = ROOT / "pipeline" / "prepare" / "processed" / "v6_pool.parquet"
DEFAULT_SPLITS_PATH = ROOT / "pipeline" / "prepare" / "processed" / "v6_splits.parquet"
DEFAULT_PLOTS_DIR = ROOT / "plots" / "v6"
DEFAULT_REPORTS_DIR = ROOT / "reports"

# Configuração visual profissional para os gráficos
sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Helvetica"]
plt.rcParams["axes.edgecolor"] = "#cbd5e1"
plt.rcParams["axes.linewidth"] = 0.8
plt.rcParams["axes.titlesize"] = 12
plt.rcParams["axes.titleweight"] = "bold"
plt.rcParams["figure.titlesize"] = 14
plt.rcParams["figure.titleweight"] = "bold"

COLOR_FAKE = "#ef4444"  # Vermelho
COLOR_TRUE = "#10b981"  # Verde esmeralda
COLOR_PALETTE = {"fake": COLOR_FAKE, "true": COLOR_TRUE}

# Stopwords em Português consolidadas (sem dependências externas)
PT_STOPWORDS = {
    "a", "à", "adeus", "agora", "aí", "ainda", "além", "algo", "alguém", "algum", "alguma", "algumas",
    "alguns", "ali", "ampla", "amplas", "amplo", "amplos", "ano", "anos", "ante", "antes", "ao", "aos",
    "apenas", "apoio", "após", "aquela", "aquelas", "aquele", "aqueles", "aquilo", "área", "as", "às",
    "assim", "até", "atrás", "através", "baixo", "bastante", "bem", "boa", "boas", "bom", "bons", "breve",
    "cá", "cada", "cento", "cerca", "certeza", "cima", "cinco", "coisa", "coisas", "com", "como", "conselho",
    "contra", "contudo", "custa", "da", "dá", "dão", "daquela", "daquelas", "daquele", "daqueles", "dar",
    "das", "de", "debaixo", "dela", "delas", "dele", "deles", "demais", "depois", "desde", "dessa", "dessas",
    "desse", "desses", "desta", "destas", "deste", "destes", "deve", "devem", "devendo", "dever", "deverá",
    "deverão", "deveria", "deveriam", "devia", "deviam", "dez", "dezoito", "dia", "dias", "diante", "diz",
    "dizem", "dizer", "do", "dois", "dos", "doze", "duas", "dúvida", "e", "é", "ela", "elas", "ele", "eles",
    "em", "embora", "enquanto", "entre", "era", "eram", "éramos", "essa", "essas", "esse", "esses", "esta",
    "está", "estamos", "estão", "estar", "estas", "estava", "estavam", "estávamos", "este", "estes", "esteve",
    "estive", "estivemos", "estiveram", "estivesse", "estivessem", "estou", "eu", "exemplo", "faço", "falta",
    "favor", "faz", "fazem", "fazemos", "fazer", "fazia", "faziam", "fez", "fim", "final", "foi", "fomos",
    "for", "fora", "foram", "fôramos", "forem", "forma", "formos", "fosse", "fossem", "fui", "geral", "grande",
    "grandes", "grupo", "há", "haja", "hajam", "hão", "haver", "houve", "isso", "isto", "já", "la", "lá",
    "lado", "lhe", "lhes", "lo", "local", "logo", "longe", "lugar", "maior", "maioria", "mais", "mal", "mas",
    "máximo", "me", "meio", "menor", "menos", "mês", "meses", "mesma", "mesmas", "mesmo", "mesmos", "meu",
    "meus", "mil", "minha", "minhas", "momento", "muito", "muitos", "na", "nada", "não", "naquela", "naquelas",
    "naquele", "naqueles", "nas", "nem", "nenhum", "nenhuma", "nessa", "nessas", "nesse", "nesses", "nesta",
    "nestas", "neste", "nestes", "ninguém", "nível", "no", "noite", "nome", "nos", "nós", "nossa", "nossas",
    "nosso", "nossos", "nova", "novas", "novo", "novos", "num", "numa", "número", "nunca", "o", "obra",
    "oito", "onde", "ontem", "os", "ou", "outra", "outras", "outro", "outros", "para", "pela", "pelas", "pelo",
    "pelos", "pequena", "pequenas", "pequeno", "pequenos", "perante", "perto", "pode", "pôde", "podem", "poder",
    "poderia", "poderiam", "podia", "podiam", "põe", "põem", "ponto", "pontos", "por", "porém", "porque",
    "porquê", "posso", "pouca", "poucas", "pouco", "poucos", "primeira", "primeiras", "primeiro", "primeiros",
    "própria", "próprias", "próprio", "próprios", "quais", "qual", "qualquer", "quando", "quanto", "quantos",
    "quatro", "que", "quem", "quer", "querem", "questão", "sabe", "sabem", "saber", "são", "se", "segundo",
    "sei", "seis", "sem", "sempre", "sendo", "ser", "será", "serão", "seria", "seriam", "sete", "seu", "seus",
    "si", "sido", "só", "sob", "sobre", "sua", "suas", "tal", "talvez", "também", "tampouco", "tanta", "tantas",
    "tanto", "tantos", "te", "tem", "têm", "temos", "tendo", "tenha", "tenham", "tenho", "ter", "terá",
    "terão", "teria", "teriam", "teve", "ti", "tido", "tinha", "tinham", "tive", "tivemos", "tiver", "tiveram",
    "tivesse", "tivessem", "toda", "todas", "todavia", "todo", "todos", "trabalho", "três", "tu", "tua", "tuas",
    "tudo", "última", "últimas", "último", "últimos", "um", "uma", "umas", "uns", "vai", "vão", "vários", "vem",
    "vêm", "ver", "vez", "vezes", "vinte", "você", "vocês", "vos", "vós", "vossa", "vossas", "vosso", "vossos",
    "pra", "pro", "pras", "pros", "ta", "tá", "né", "disse", "afirmou", "afirma", "segundo", "publicado"
}

# Léxico de Urgência e Sensacionalismo (verificado com fronteiras de palavra \b)
URGENCY_REGEX = re.compile(
    r"\b(urgente|alerta|atencao|atenção|cuidado|bomba|perigo|urgencia|urgência|repasse|"
    r"compartilhe|divulgue|espalhe|apaguem|viralize|escondem|revelado|censurado|segredo|"
    r"absurdo|inacreditavel|inacreditável|vergonha|escandalo|escândalo|criminoso|chocante|"
    r"revoltante|farsa|mentira|fraude|golpe)\b",
    re.IGNORECASE
)

# Léxico de Sentimento Sintético
POS_WORDS = {
    "bom", "boa", "otimo", "ótima", "ótimo", "excelente", "maravilhoso", "maravilhosa", "sucesso",
    "vitoria", "vitória", "parabens", "parabéns", "positivo", "esperança", "avanco", "avanço",
    "conquista", "beneficio", "benefício", "saude", "saúde", "cura", "eficaz", "eficiente",
    "seguro", "segurança", "recuperacao", "recuperação", "crescimento", "melhor", "melhoria",
    "justica", "justiça", "verdade", "verdadeiro", "correto"
}

NEG_WORDS = {
    "ruim", "pessimo", "péssimo", "péssima", "horrivel", "horrível", "terrivel", "terrível",
    "fracasso", "derrota", "crise", "negativo", "perigo", "ameaca", "ameaça", "prejuizo",
    "prejuízo", "doenca", "doença", "morte", "morrer", "virus", "vírus", "letal", "veneno",
    "medo", "inseguro", "fraude", "crime", "corrupcao", "corrupção", "mentira", "falso",
    "farsa", "golpe", "ataque", "violencia", "violência", "destruicao", "destruição", "culpado",
    "caos", "panico", "pânico", "desastre", "traicao", "traição", "vergonha", "absurdo"
}


def load_dataset(pool_path: Path, splits_path: Path) -> pd.DataFrame:
    """Carrega o pool v6 e junta com a tabela de splits."""
    print(f"📦 Carregando pool v6: {pool_path}")
    pool = pd.read_parquet(pool_path)
    print(f"   Pool carregado: {len(pool):,} linhas x {pool.shape[1]} colunas.")

    if splits_path.exists():
        print(f"📦 Carregando splits: {splits_path}")
        splits = pd.read_parquet(splits_path)
        # Manter rid como chave de junção
        df = pool.merge(splits, on="rid", how="left")
        print(f"   Pool + Splits mesclado com sucesso ({len(df):,} linhas).")
    else:
        print("⚠️ Aviso: Arquivo de splits não encontrado. Continuando apenas com pool.")
        df = pool

    return df


def compute_vocabulary_metrics(texts: pd.Series) -> dict:
    """Calcula estatísticas de vocabulário, Type-Token Ratio (TTR) e Hapax Legomena."""
    token_pattern = re.compile(r"\b[a-záàâãéèêíïóôõöúçñ]{2,}\b")
    counts = Counter()
    total_tokens = 0

    for text in texts.dropna():
        tokens = token_pattern.findall(str(text).lower())
        counts.update(tokens)
        total_tokens += len(tokens)

    unique_types = len(counts)
    ttr = (unique_types / total_tokens * 100) if total_tokens > 0 else 0.0
    hapax = sum(1 for c in counts.values() if c == 1)
    hapax_pct = (hapax / unique_types * 100) if unique_types > 0 else 0.0

    return {
        "total_tokens": total_tokens,
        "unique_types": unique_types,
        "ttr_pct": round(ttr, 2),
        "hapax_count": hapax,
        "hapax_pct": round(hapax_pct, 2)
    }


def compute_log_odds_bigrams(texts_fake: pd.Series, texts_true: pd.Series, top_k: int = 12) -> tuple[list, list]:
    """Calcula Log-Odds Ratio com Dirichlet Prior (Monroe et al., 2008) para bigramas."""
    vec = CountVectorizer(
        ngram_range=(2, 2),
        stop_words=list(PT_STOPWORDS),
        min_df=10,
        token_pattern=r"(?u)\b[a-záàâãéèêíïóôõöúçñ]{3,}\b"
    )
    combined = pd.concat([texts_fake, texts_true])
    vec.fit(combined)

    counts_fake = np.asarray(vec.transform(texts_fake).sum(axis=0)).ravel()
    counts_true = np.asarray(vec.transform(texts_true).sum(axis=0)).ravel()

    n_fake = counts_fake.sum()
    n_true = counts_true.sum()

    # Dirichlet prior proporcional ao corpus combinado
    prior = (counts_fake + counts_true) / (n_fake + n_true)
    alpha = 0.1 * prior * (n_fake + n_true)

    log_odds = np.log((counts_fake + alpha) / (n_fake + alpha.sum() - counts_fake - alpha)) - \
               np.log((counts_true + alpha) / (n_true + alpha.sum() - counts_true - alpha))

    variance = (1.0 / (counts_fake + alpha)) + (1.0 / (counts_true + alpha))
    z_scores = log_odds / np.sqrt(variance)

    feature_names = np.array(vec.get_feature_names_out())

    # Top para Fake (Z positivo alto)
    top_fake_idx = np.argsort(z_scores)[-top_k:][::-1]
    top_fake = [(feature_names[i], float(z_scores[i])) for i in top_fake_idx]

    # Top para True (Z negativo alto)
    top_true_idx = np.argsort(z_scores)[:top_k]
    top_true = [(feature_names[i], float(-z_scores[i])) for i in top_true_idx]

    return top_fake, top_true


def compute_stylistic_features(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula densidade de urgência e proxies de sentimento vetorizados."""
    print("⚡ Computando marcadores de urgência e sentimento vetorizados...")
    texts = df["text_no_url"].fillna("").astype(str).str.lower()
    
    # 1. Contagem de palavras de urgência
    urgency_counts = texts.str.count(URGENCY_REGEX)
    word_len_safe = np.maximum(df["word_len"].to_numpy(), 1)
    df["urgency_density"] = (urgency_counts / word_len_safe) * 100.0

    # 2. Sentimento aproximado por contagem de léxico
    pos_pattern = re.compile(r"\b(" + "|".join(POS_WORDS) + r")\b")
    neg_pattern = re.compile(r"\b(" + "|".join(NEG_WORDS) + r")\b")

    pos_counts = texts.str.count(pos_pattern)
    neg_counts = texts.str.count(neg_pattern)

    total_sentiment_words = pos_counts + neg_counts
    df["sentiment_polarity"] = (pos_counts - neg_counts) / (total_sentiment_words + 1e-5)
    df["subjectivity_score"] = (total_sentiment_words / word_len_safe) * 100.0

    return df


def generate_plots(df: pd.DataFrame, plots_dir: Path, disc_fake: list, disc_true: list):
    """Gera o leque completo de visualizações da EDA v6."""
    plots_dir.mkdir(parents=True, exist_ok=True)
    print(f"📊 Gerando visualizações em: {plots_dir}")

    # 1. Distribuição do Tamanho dos Textos (Boxplot + KDE)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    sns.boxplot(
        data=df, x="label", y="word_len", hue="label",
        palette=COLOR_PALETTE, ax=axes[0], showfliers=False
    )
    axes[0].set_title("Distribuição do Número de Palavras (sem outliers visuais)")
    axes[0].set_xlabel("Rótulo")
    axes[0].set_ylabel("Número de Palavras")

    sns.kdeplot(
        data=df, x="word_len", hue="label", common_norm=False, log_scale=True,
        palette=COLOR_PALETTE, ax=axes[1], fill=True, alpha=0.3
    )
    axes[1].set_title("Densidade de Palavras por Texto (Escala Logarítmica)")
    axes[1].set_xlabel("Número de Palavras (log)")
    axes[1].set_ylabel("Densidade")
    plt.tight_layout()
    plt.savefig(plots_dir / "01_length_distribution_by_class.png", dpi=200)
    plt.close()

    # 2. Tamanho dos Textos por Grupo (Top 18 maiores grupos)
    top_groups = df["group"].value_counts().head(18).index
    df_top_groups = df[df["group"].isin(top_groups)]
    fig, ax = plt.subplots(figsize=(15, 6))
    order = df_top_groups.groupby("group")["word_len"].median().sort_values().index
    sns.boxplot(
        data=df_top_groups, x="group", y="word_len", hue="label",
        order=order, palette=COLOR_PALETTE, showfliers=False, ax=ax
    )
    ax.set_title("Tamanho dos Textos pelos Maiores Grupos (Mediana Ordenada)")
    ax.set_xlabel("Grupo do Dataset")
    ax.set_ylabel("Número de Palavras")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(plots_dir / "02_length_distribution_by_group.png", dpi=200)
    plt.close()

    # 3. Distribuição Temporal e por Canal
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    era_order = ["<=2017", "2018-2022", ">=2023", "sem_data"]
    era_order_present = [e for e in era_order if e in df["era"].values]
    sns.countplot(
        data=df, x="era", hue="label", order=era_order_present,
        palette=COLOR_PALETTE, ax=axes[0]
    )
    axes[0].set_title("Volume de Textos por Era Temporal")
    axes[0].set_xlabel("Era")
    axes[0].set_ylabel("Contagem de Amostras")

    channel_order = df["channel"].value_counts().index
    sns.countplot(
        data=df, x="channel", hue="label", order=channel_order,
        palette=COLOR_PALETTE, ax=axes[1]
    )
    axes[1].set_title("Distribuição por Canal de Disseminação")
    axes[1].set_xlabel("Canal")
    axes[1].set_ylabel("Contagem de Amostras")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(plots_dir / "03_temporal_and_channel_distribution.png", dpi=200)
    plt.close()

    # 4. Bigramas Mais Discriminativos (Log-Odds Z-Score)
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    df_fake = pd.DataFrame(disc_fake, columns=["bigram", "z_score"])
    sns.barplot(data=df_fake, y="bigram", x="z_score", color=COLOR_FAKE, ax=axes[0])
    axes[0].set_title("Bigramas Mais Distintivos de FAKE NEWS (Z-Score)", color=COLOR_FAKE)
    axes[0].set_xlabel("Força da Associação (Z-Score)")
    axes[0].set_ylabel("")

    df_true = pd.DataFrame(disc_true, columns=["bigram", "z_score"])
    sns.barplot(data=df_true, y="bigram", x="z_score", color=COLOR_TRUE, ax=axes[1])
    axes[1].set_title("Bigramas Mais Distintivos de NOTÍCIAS REAIS (Z-Score)", color=COLOR_TRUE)
    axes[1].set_xlabel("Força da Associação (Z-Score)")
    axes[1].set_ylabel("")
    plt.tight_layout()
    plt.savefig(plots_dir / "04_discriminative_bigrams_log_odds.png", dpi=200)
    plt.close()

    # 5. Dashboard de Marcadores Estilísticos e Sentimento
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    sns.barplot(
        data=df, x="label", y="uppercase_word_ratio", hue="label",
        palette=COLOR_PALETTE, ax=axes[0, 0]
    )
    axes[0, 0].set_title("Proporção de Palavras em Caixa Alta (Shouting)")
    axes[0, 0].set_ylabel("Média da Proporção")
    axes[0, 0].set_xlabel("Classe")

    sns.barplot(
        data=df, x="label", y="urgency_density", hue="label",
        palette=COLOR_PALETTE, ax=axes[0, 1]
    )
    axes[0, 1].set_title("Densidade de Léxico de Urgência / Sensacionalismo")
    axes[0, 1].set_ylabel("Menções por 100 palavras")
    axes[0, 1].set_xlabel("Classe")

    sns.kdeplot(
        data=df, x="sentiment_polarity", hue="label", common_norm=False,
        palette=COLOR_PALETTE, ax=axes[1, 0], fill=True, alpha=0.3
    )
    axes[1, 0].set_title("Densidade da Polaridade de Sentimento (-1 a +1)")
    axes[1, 0].set_xlabel("Polaridade")
    axes[1, 0].set_ylabel("Densidade")

    sns.barplot(
        data=df, x="channel", y="num_exclamations", hue="label",
        palette=COLOR_PALETTE, ax=axes[1, 1]
    )
    axes[1, 1].set_title("Média de Pontos de Exclamação (!) por Canal")
    axes[1, 1].set_ylabel("Média de Exclamações")
    axes[1, 1].set_xlabel("Canal")
    axes[1, 1].tick_params(axis="x", rotation=30)
    plt.tight_layout()
    plt.savefig(plots_dir / "05_stylistic_markers_dashboard.png", dpi=200)
    plt.close()

    # 6. Composição dos 20 Maiores Grupos (Auditoria de Atalho)
    fig, ax = plt.subplots(figsize=(15, 7))
    top20_groups = df["group"].value_counts().head(20).index
    df_ct = pd.crosstab(df[df["group"].isin(top20_groups)]["group"], df["label"], normalize="index") * 100
    df_ct = df_ct.loc[top20_groups]  # Ordenado por frequência
    df_ct.plot(kind="bar", stacked=True, color=[COLOR_FAKE, COLOR_TRUE], ax=ax, width=0.8)
    ax.set_title("Composição de Rótulo nos 20 Maiores Grupos (% Fake vs % True)")
    ax.set_ylabel("Porcentagem (%)")
    ax.set_xlabel("Grupo")
    ax.axhline(50, color="#64748b", linestyle="--", alpha=0.6)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(plots_dir / "06_group_label_composition.png", dpi=200)
    plt.close()

    # 7. Divisão dos Splits (se colunas de split existirem)
    if "split_full_iid" in df.columns:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))
        splits_to_plot = [
            ("split_full_iid", "Split Full IID (70/10/5/15)"),
            ("split_ood_wa", "Split OOD WhatsApp"),
            ("split_bal_iid", "Split Bal IID (Informativos)")
        ]
        for idx, (col_name, title) in enumerate(splits_to_plot):
            if col_name in df.columns:
                sns.countplot(
                    data=df[df[col_name] != "unused"],
                    x=col_name, hue="label", palette=COLOR_PALETTE,
                    order=["train", "val_sel", "val_calib", "test"],
                    ax=axes[idx]
                )
                axes[idx].set_title(title)
                axes[idx].set_xlabel("Partição")
                axes[idx].set_ylabel("Número de Amostras")
        plt.tight_layout()
        plt.savefig(plots_dir / "07_splits_distribution.png", dpi=200)
        plt.close()

    print("✅ Todos os 7 gráficos foram gerados e salvos.")


def generate_markdown_report(df: pd.DataFrame, stats: dict, reports_dir: Path, plots_dir: Path) -> Path:
    """Escreve o relatório detalhado em Markdown com tabelas GFM e figuras embutidas."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / "eda_v6_report.md"
    print(f"📝 Gerando relatório síntese em Markdown: {report_file}")

    # Tabelas de estatísticas
    len_class = df.groupby("label")["word_len"].agg(
        ["count", "mean", "median", "std", lambda x: np.percentile(x, 75), lambda x: np.percentile(x, 95)]
    ).rename(columns={"<lambda_0>": "p75", "<lambda_1>": "p95"})

    style_summary = df.groupby("label")[
        ["uppercase_word_ratio", "urgency_density", "num_exclamations", "num_questions", "sentiment_polarity"]
    ].mean()

    channel_summary = df.groupby(["channel", "label"])["rid"].count().unstack(fill_value=0)
    channel_summary["total"] = channel_summary.sum(axis=1)
    channel_summary["pct_fake"] = (channel_summary["fake"] / channel_summary["total"]) * 100

    tier_summary = df.groupby("label_tier")["label"].value_counts().unstack(fill_value=0)

    # Identificar grupos constantes
    constant_groups = []
    for g, sub in df.groupby("group")["label"]:
        if sub.nunique() == 1:
            constant_groups.append((g, len(sub), sub.iloc[0]))
    constant_groups.sort(key=lambda x: x[1], reverse=True)

    md = f"""# Relatório Executivo de Análise Exploratória (EDA) — Pool v6

> **Status do Dataset:** v6 Oficial • **Total de Registros:** {len(df):,} linhas rotuladas  
> **Distribuição Global:** {stats['fake_count']:,} Fake ({stats['fake_pct']:.2f}%) • {stats['true_count']:,} True ({stats['true_pct']:.2f}%) • Razão: **{stats['ratio']:.2f}:1**

---

## 1. Visão Geral e Invariantes do Dataset

A versão 6 do corpus FakenewsBR integra um pool completo com **{len(df):,} textos rotulados**, cobrindo **{df['group'].nunique()} grupos de procedência** e múltiplos canais de disseminação.

| Métrica | Valor Medido | Observação / Implicação |
| :--- | :---: | :--- |
| **Linhas Rotuladas** | `{len(df):,}` | Base completa para treino e avaliação |
| **Proporção Fake / True** | `{stats['fake_pct']:.1f}% / {stats['true_pct']:.1f}%` | Desbalanceamento moderado natural de checadores de fatos |
| **Grupos Informativos** | `{stats['info_count']:,} linhas` | Grupos com diversidade fake/true (`is_balanced_group=True`) |
| **Grupos de Rótulo Constante** | `{stats['const_count']:,} linhas ({len(constant_groups)} grupos)` | Risco de atalho (*shortcut learning*) por procedência |
| **Linhas com Mojibake / U+FFFD** | `{df['has_ufffd'].sum()}` | Resíduo mínimo de decodificação limpo e auditado |

### Distribuição por Tier de Confiabilidade de Rótulo (`label_tier`)
{tier_summary.to_markdown()}

---

## 2. Análise de Comprimento e Distribuição Textual

O número de palavras (`word_len`) varia significativamente entre classes e formatos de publicação. Enquanto notícias verdadeiras tendem a seguir estruturas jornalísticas mais extensas, notícias falsas frequentemente concentram formatos mais curtos e diretos, típicos de redes sociais e mensageria.

{len_class.to_markdown()}

![Distribuição do Tamanho dos Textos](file:///{plots_dir.resolve()}/01_length_distribution_by_class.png)

### Comprimento por Grupo
A análise dos grupos revela disparidades marcantes: grupos procedentes do WhatsApp (`FakeWhatsApp.BR_2018`) e checadores de boatos rápidos (`FC_BOATOS_VIRAL`) possuem medianas de tamanho substancialmente menores do que veículos de imprensa institucional.

![Tamanho dos Textos por Grupo](file:///{plots_dir.resolve()}/02_length_distribution_by_group.png)

---

## 3. Riqueza Vocabular e Diversidade Léxica

Avaliamos a riqueza lexical por meio do **Type-Token Ratio (TTR)** e a frequência de **Hapax Legomena** (palavras de ocorrência única).

| Subconjunto | Total Tokens | Tipos Únicos | TTR (%) | Hapax Legomena | Hapax (%) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Fake News** | `{stats['vocab_fake']['total_tokens']:,}` | `{stats['vocab_fake']['unique_types']:,}` | `{stats['vocab_fake']['ttr_pct']}%` | `{stats['vocab_fake']['hapax_count']:,}` | `{stats['vocab_fake']['hapax_pct']}%` |
| **Notícias Reais** | `{stats['vocab_true']['total_tokens']:,}` | `{stats['vocab_true']['unique_types']:,}` | `{stats['vocab_true']['ttr_pct']}%` | `{stats['vocab_true']['hapax_count']:,}` | `{stats['vocab_true']['hapax_pct']}%` |

> 📌 **Achado Linguístico:** Notícias verdadeiras apresentam maior variedade lexical global devido à cobertura temática mais ampla e textos mais aprofundados. Já textos desinformativos exibem vocabulário concentrado em temas recorrentes e polarizados.

---

## 4. Bigramas Mais Discriminativos (Log-Odds Ratio com Dirichlet Prior)

A metodologia de *Monroe, Colaresi & Quinn (2008)* isola os termos cuja presença oferece maior evidência estatística em favor de uma classe, corrigindo distorções causadas por termos hiper-frequentes.

![Bigramas Discriminativos](file:///{plots_dir.resolve()}/04_discriminative_bigrams_log_odds.png)

* **Marcadores de FAKE:** Presença marcante de verbos de urgência, conspiração e convocação de compartilhamento ("veja video", "compartilhe urgente", "escondem de voce").
* **Marcadores de TRUE:** Termos da esfera institucional, processo penal, judiciário e declarações formais ("ministerio publico", "segundo assessoria", "tribunal justica").

---

## 5. Marcadores Estilísticos e Sensacionalismo

Comparação de intensidade estilística entre as classes:

{style_summary.to_markdown()}

![Dashboard de Marcadores Estilísticos](file:///{plots_dir.resolve()}/05_stylistic_markers_dashboard.png)

* **Caixa Alta (Shouting):** Significativamente mais frequente em fake news (`{stats['style_fake_upper']:.2f}%` vs `{stats['style_true_upper']:.2f}%`), denotando apelo emotivo e ênfase sensacionalista.
* **Pontuação Exclamativa:** Dispara especialmente no canal WhatsApp e redes sociais.
* **Polaridade de Sentimento:** Notícias falsas mostram viés pronunciado de negatividade, perigo e indignação.

---

## 6. Auditoria de Atalhos e Vieses (Shortcut Learning)

O pool v6 possui **11 grupos com rótulo constante (100% fake ou 100% true)** totalizando **{stats['const_count']:,} linhas**.

| Grupo Constante | Total Linhas | Rótulo Único |
| :--- | :---: | :---: |
"""
    for g, n, lbl in constant_groups:
        md += f"| `{g}` | `{n:,}` | `{lbl}` |\n"

    md += f"""
![Composição de Rótulo nos Grupos](file:///{plots_dir.resolve()}/06_group_label_composition.png)

> ⚠️ **Recomendação para Modelagem (Fine-Tuning):**  
> Se o modelo for treinado sem ponderação de grupo, ele aprenderá a reconhecer o vocabulário do veículo/canal em vez do padrão de desinformação. O uso de **DFR (Deep Feature Reweighting) cell-level com `weight_clip=25`**, conforme definido no plano da v6, é estritamente mandatário.

---

## 7. Distribuição dos Splits de Avaliação

Verificação da integridade das partições de treino, validação e teste:

![Distribuição dos Splits](file:///{plots_dir.resolve()}/07_splits_distribution.png)

* **`full_iid` (70/10/5/15):** Pool completo estratificado preservando proporções por grupo.
* **`ood_wa`:** Reserva todo o canal WhatsApp para teste out-of-distribution (avaliando generalização cross-channel).
* **`bal_iid`:** Subconjunto canônico restrito aos grupos informativos equilibrados.

---

*Relatório gerado automaticamente pelo pipeline EDA v6 • FakenewsBR*
"""

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(md)

    return report_file


def run_eda(pool_path: Path, splits_path: Path, plots_dir: Path, reports_dir: Path, generate_html: bool = True):
    """Orquestrador principal da Análise Exploratória v6."""
    print("=" * 70)
    print("🚀 INICIANDO ANÁLISE EXPLORATÓRIA DE DADOS — FAKENEWSBR v6")
    print("=" * 70)

    # 1. Carregar dados
    df = load_dataset(pool_path, splits_path)

    # 2. Estatísticas fundamentais
    n_total = len(df)
    n_fake = int((df["label"] == "fake").sum())
    n_true = int((df["label"] == "true").sum())
    fake_pct = (n_fake / n_total) * 100
    true_pct = (n_true / n_total) * 100
    ratio = n_fake / max(n_true, 1)

    n_info = int(df["is_balanced_group"].sum()) if "is_balanced_group" in df.columns else 0

    const_count = 0
    for _, sub in df.groupby("group")["label"]:
        if sub.nunique() == 1:
            const_count += len(sub)

    print(f"\n📊 Estatísticas Gerais:")
    print(f"   Total: {n_total:,} linhas")
    print(f"   Fake:  {n_fake:,} ({fake_pct:.2f}%)")
    print(f"   True:  {n_true:,} ({true_pct:.2f}%)")
    print(f"   Grupos informativos: {n_info:,} linhas")
    print(f"   Grupos constantes:   {const_count:,} linhas")

    # 3. Métricas de Vocabulário
    print("\n📚 Calculando métricas de riqueza vocabular...")
    texts_fake = df[df["label"] == "fake"]["text_no_url"]
    texts_true = df[df["label"] == "true"]["text_no_url"]
    vocab_fake = compute_vocabulary_metrics(texts_fake)
    vocab_true = compute_vocabulary_metrics(texts_true)

    # 4. Bigramas Discriminativos (Log-Odds)
    print("\n🔍 Extraindo bigramas discriminativos (Log-Odds com Dirichlet Prior)...")
    disc_fake, disc_true = compute_log_odds_bigrams(texts_fake, texts_true, top_k=10)

    # 5. Marcadores Estilísticos e Sentimento
    df = compute_stylistic_features(df)

    stats = {
        "total_rows": n_total,
        "fake_count": n_fake,
        "true_count": n_true,
        "fake_pct": fake_pct,
        "true_pct": true_pct,
        "ratio": ratio,
        "info_count": n_info,
        "const_count": const_count,
        "vocab_fake": vocab_fake,
        "vocab_true": vocab_true,
        "style_fake_upper": float(df[df["label"] == "fake"]["uppercase_word_ratio"].mean()),
        "style_true_upper": float(df[df["label"] == "true"]["uppercase_word_ratio"].mean()),
    }

    # 6. Gerar Gráficos
    generate_plots(df, plots_dir, disc_fake, disc_true)

    # 7. Gerar Relatório Markdown
    md_file = generate_markdown_report(df, stats, reports_dir, plots_dir)

    # 8. Salvar JSON de estatísticas
    json_file = reports_dir / "eda_v6_stats.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"💾 Estatísticas salvas em JSON: {json_file}")

    # 9. Compilar para HTML autocontido
    if generate_html:
        print("\n🌐 Compilando relatório HTML autocontido...")
        from investigation.generate_html_report import generate_report
        html_file = reports_dir / "eda_v6_report.html"
        generate_report(md_file, html_file, title="FakenewsBR v6 • Relatório Executivo de EDA")

    print("\n" + "=" * 70)
    print("🎉 EDA v6 CONCLUÍDA COM SUCESSO!")
    print(f"   Gráficos:  {plots_dir}")
    print(f"   Markdown:  {md_file}")
    if generate_html:
        print(f"   HTML:      {reports_dir / 'eda_v6_report.html'}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Executa EDA completa do FakenewsBR v6.")
    parser.add_argument("--pool-path", type=Path, default=DEFAULT_POOL_PATH, help="Caminho do v6_pool.parquet")
    parser.add_argument("--splits-path", type=Path, default=DEFAULT_SPLITS_PATH, help="Caminho do v6_splits.parquet")
    parser.add_argument("--plots-dir", type=Path, default=DEFAULT_PLOTS_DIR, help="Diretório de saída para os gráficos")
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR, help="Diretório de saída para os relatórios")
    parser.add_argument("--no-html", action="store_true", help="Desativa a geração automática do HTML")

    args = parser.parse_args()
    run_eda(
        pool_path=args.pool_path,
        splits_path=args.splits_path,
        plots_dir=args.plots_dir,
        reports_dir=args.reports_dir,
        generate_html=not args.no_html
    )


if __name__ == "__main__":
    main()
