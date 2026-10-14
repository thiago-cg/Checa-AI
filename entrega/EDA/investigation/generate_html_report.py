#!/usr/bin/env python3
"""generate_html_report.py -- Compilador de relatórios Markdown para HTML autocontido.

Converte relatórios Markdown em documentos HTML modernos e estilizados,
incorporando todas as imagens locais em Base64 (Data URI) para que o arquivo
HTML seja 100% autocontido e portátil (pode ser compartilhado sem dependências externas).
Funciona de forma agnóstica de sistema operacional (macOS, Linux, Windows).
"""

from __future__ import annotations

import argparse
import base64
import mimetypes
import os
import re
import sys
from pathlib import Path

# Raiz do repositório
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MD_PATH = REPO_ROOT / "reports" / "eda_v6_report.md"
DEFAULT_HTML_PATH = REPO_ROOT / "reports" / "eda_v6_report.html"


def get_base64_encoded_image(image_path: Path) -> str:
    """Lê uma imagem local e retorna a string Data URI em base64 com mime-type correto."""
    if not image_path.exists() or not image_path.is_file():
        return ""
    
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type:
        ext = image_path.suffix.lower()
        if ext in (".png", ".webp"):
            mime_type = f"image/{ext[1:]}"
        elif ext in (".jpg", ".jpeg"):
            mime_type = "image/jpeg"
        elif ext == ".svg":
            mime_type = "image/svg+xml"
        else:
            mime_type = "image/png"

    with open(image_path, "rb") as img_file:
        encoded = base64.b64encode(img_file.read()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"


def resolve_image_path(raw_path: str, md_dir: Path) -> Path | None:
    """Resolve o caminho da imagem tratando prefixos de URL, caminhos relativos e absolutos."""
    clean = raw_path.strip()
    # Remove prefixo file:// ou file:///
    clean = re.sub(r"^file:///?", "", clean)
    
    # Tratamento para caminhos Windows colados em Unix ou vice-versa
    if os.name != "nt" and re.match(r"^[a-zA-Z]:[/\\]", clean):
        # Se for um caminho absoluto de Windows no Mac/Linux, tenta achar pelo nome do arquivo
        fname = Path(clean.replace("\\", "/")).name
        # Tenta na pasta plots do repo
        candidate = REPO_ROOT / "plots" / "v6" / fname
        if candidate.exists():
            return candidate
        candidate2 = REPO_ROOT / "plots" / fname
        if candidate2.exists():
            return candidate2

    p = Path(clean)
    if p.is_absolute() and p.exists():
        return p

    # 1. Relativo ao diretório do markdown
    cand1 = (md_dir / p).resolve()
    if cand1.exists():
        return cand1

    # 2. Relativo à raiz do repositório
    cand2 = (REPO_ROOT / p).resolve()
    if cand2.exists():
        return cand2

    # 3. Relativo a plots/v6/
    cand3 = (REPO_ROOT / "plots" / "v6" / p.name).resolve()
    if cand3.exists():
        return cand3

    return None


def convert_md_to_html(md_text: str, md_dir: Path) -> str:
    """Converte markdown em HTML com imagens convertidas em Data URI base64."""
    # 1. Converter imagens em base64
    img_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'

    def img_replacer(match: re.Match) -> str:
        alt_text = match.group(1)
        raw_path = match.group(2)
        resolved = resolve_image_path(raw_path, md_dir)

        if resolved and resolved.exists():
            data_uri = get_base64_encoded_image(resolved)
            return (
                f'<figure class="report-figure">\n'
                f'  <img src="{data_uri}" alt="{alt_text}" loading="lazy"/>\n'
                f'  <figcaption>{alt_text}</figcaption>\n'
                f'</figure>'
            )
        else:
            return (
                f'<div class="img-missing-badge">'
                f'⚠️ <em>[Imagem não encontrada: {alt_text} — caminho: {raw_path}]</em>'
                f'</div>'
            )

    md_text_images = re.sub(img_pattern, img_replacer, md_text)

    # 2. Renderizar Markdown para HTML
    try:
        import markdown
        html_body = markdown.markdown(
            md_text_images,
            extensions=["tables", "fenced_code", "toc", "sane_lists"]
        )
    except ImportError:
        print("Aviso: Módulo 'markdown' não encontrado. Usando conversor básico.")
        # Fallback ultra-simples para parágrafos e cabeçalhos
        lines = md_text_images.split("\n")
        out = []
        for line in lines:
            if line.startswith("# "):
                out.append(f"<h1>{line[2:]}</h1>")
            elif line.startswith("## "):
                out.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("### "):
                out.append(f"<h3>{line[4:]}</h3>")
            elif line.strip() == "":
                out.append("<br/>")
            else:
                out.append(f"<p>{line}</p>")
        html_body = "\n".join(out)

    return html_body


CSS_STYLES = """
:root {
    --primary: #1e293b;
    --primary-light: #334155;
    --accent: #2563eb;
    --accent-hover: #1d4ed8;
    --accent-light: #eff6ff;
    --success: #16a34a;
    --warning: #d97706;
    --danger: #dc2626;
    --bg-main: #f8fafc;
    --bg-card: #ffffff;
    --text-main: #0f172a;
    --text-muted: #64748b;
    --border: #e2e8f0;
    --border-subtle: #f1f5f9;
    --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
    --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
    --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
    --radius-sm: 6px;
    --radius-md: 10px;
    --radius-lg: 16px;
}

* {
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    line-height: 1.65;
    color: var(--text-main);
    background-color: var(--bg-main);
    margin: 0;
    padding: 30px 20px;
}

.report-wrapper {
    max-width: 1200px;
    margin: 0 auto;
    background: var(--bg-card);
    padding: 48px;
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-lg);
    border: 1px solid var(--border);
}

.header-banner {
    border-bottom: 2px solid var(--border);
    padding-bottom: 24px;
    margin-bottom: 36px;
}

.header-badge {
    display: inline-block;
    background: var(--accent-light);
    color: var(--accent);
    font-size: 0.85em;
    font-weight: 700;
    padding: 4px 12px;
    border-radius: 9999px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 12px;
}

h1, h2, h3, h4 {
    color: var(--primary);
    font-weight: 700;
    line-height: 1.25;
}

h1 {
    font-size: 2.3rem;
    margin-top: 0;
    margin-bottom: 12px;
    color: var(--primary);
}

h2 {
    font-size: 1.6rem;
    margin-top: 40px;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--accent-light);
    display: flex;
    align-items: center;
    gap: 8px;
}

h3 {
    font-size: 1.25rem;
    margin-top: 28px;
    margin-bottom: 12px;
    color: var(--primary-light);
}

p {
    margin-top: 0;
    margin-bottom: 1.1em;
    color: #334155;
    font-size: 1rem;
}

blockquote {
    border-left: 4px solid var(--accent);
    background-color: var(--accent-light);
    padding: 16px 20px;
    margin: 24px 0;
    border-radius: 0 var(--radius-md) var(--radius-md) 0;
    color: #1e3a8a;
    font-size: 0.98rem;
}

blockquote p:last-child {
    margin-bottom: 0;
}

table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    margin: 28px 0;
    font-size: 0.92rem;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    overflow: hidden;
    box-shadow: var(--shadow-sm);
}

table thead tr {
    background: #f1f5f9;
    color: var(--primary);
    font-weight: 600;
    text-align: left;
}

table th, table td {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
}

table tbody tr:last-child td {
    border-bottom: none;
}

table tbody tr:nth-of-type(even) {
    background-color: #f8fafc;
}

table tbody tr:hover {
    background-color: #f1f5f9;
    transition: background-color 0.15s ease-in-out;
}

.report-figure {
    margin: 36px 0;
    text-align: center;
    background: #ffffff;
    padding: 16px;
    border-radius: var(--radius-md);
    border: 1px solid var(--border);
    box-shadow: var(--shadow-md);
}

.report-figure img {
    max-width: 100%;
    height: auto;
    border-radius: var(--radius-sm);
    display: block;
    margin: 0 auto;
}

.report-figure figcaption {
    margin-top: 12px;
    font-size: 0.9rem;
    color: var(--text-muted);
    font-style: italic;
    font-weight: 500;
}

.img-missing-badge {
    background: #fef2f2;
    color: var(--danger);
    padding: 12px 16px;
    border-radius: var(--radius-sm);
    border: 1px dashed #fca5a5;
    margin: 20px 0;
    font-size: 0.9rem;
}

code {
    background-color: #f1f5f9;
    color: #e11d48;
    padding: 3px 6px;
    border-radius: 4px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.88em;
}

pre {
    background-color: #0f172a;
    color: #e2e8f0;
    padding: 18px 22px;
    border-radius: var(--radius-md);
    overflow-x: auto;
    font-size: 0.88rem;
    line-height: 1.5;
}

pre code {
    background-color: transparent;
    color: inherit;
    padding: 0;
}

hr {
    border: none;
    border-top: 1px solid var(--border);
    margin: 36px 0;
}

.footer {
    margin-top: 48px;
    padding-top: 24px;
    border-top: 1px solid var(--border);
    font-size: 0.85rem;
    color: var(--text-muted);
    text-align: center;
}

@media print {
    body {
        background: #ffffff;
        padding: 0;
    }
    .report-wrapper {
        border: none;
        box-shadow: none;
        padding: 0;
        max-width: 100%;
    }
}
"""


def build_full_html(html_body: str, title: str) -> str:
    """Monta a página HTML completa com meta-tags e estilo embutido."""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
{CSS_STYLES}
    </style>
</head>
<body>
    <div class="report-wrapper">
        <header class="header-banner">
            <span class="header-badge">FakenewsBR • Análise Exploratória v6</span>
            <div style="font-size: 0.88rem; color: #64748b; margin-top: 4px;">
                Relatório gerado automaticamente a partir dos dados do pool v6
            </div>
        </header>
        <main>
{html_body}
        </main>
        <footer class="footer">
            FakenewsBR v6 • Projeto de Detecção de Desinformação em Língua Portuguesa
        </footer>
    </div>
</body>
</html>"""


def generate_report(md_path: Path, html_path: Path, title: str = "Relatório EDA - FakenewsBR v6") -> bool:
    """Executa a conversão e geração do arquivo HTML."""
    if not md_path.exists():
        print(f"Erro: Arquivo Markdown não encontrado em: {md_path}")
        return False

    print(f"Lendo relatório Markdown: {md_path}")
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    print("Processando imagens e convertendo para Base64...")
    html_body = convert_md_to_html(md_text, md_path.parent)

    print("Construindo documento HTML final...")
    full_html = build_full_html(html_body, title)

    html_path.parent.mkdir(parents=True, exist_ok=True)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(full_html)

    size_kb = html_path.stat().st_size / 1024
    print(f"✅ Relatório HTML gerado com sucesso em: {html_path} ({size_kb:.1f} KB)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Compila relatório Markdown para HTML autocontido com imagens embutidas.")
    parser.add_argument("--input", "-i", type=Path, default=DEFAULT_MD_PATH, help="Caminho do arquivo Markdown de entrada.")
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_HTML_PATH, help="Caminho do arquivo HTML de saída.")
    parser.add_argument("--title", "-t", type=str, default="FakenewsBR v6 - Análise Exploratória de Dados (EDA)", help="Título do documento HTML.")

    args = parser.parse_args()
    success = generate_report(args.input, args.output, args.title)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
