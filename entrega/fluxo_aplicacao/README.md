# Checa AI — Desenho do Fluxo e Arquitetura da Aplicação

Este diretório contém a documentação e os diagramas oficiais do **desenho do fluxo e arquitetura da aplicação Checa AI (CrossCheckBR)**.

---

## 📁 Arquivos Disponíveis

| Arquivo | Descrição |
|---|---|
| [`FLUXO_APLICACAO.md`](FLUXO_APLICACAO.md) | **Documento Técnico Principal em Markdown** contendo a especificação detalhada de ponta a ponta, diagramas Mermaid (macro-fluxo, sequência, decisão bayesiana e resiliência), mapeamento das 12 etapas, contratos de dados e rastreabilidade com os requisitos (RF e RNF). |
| [`fluxo_aplicacao.html`](fluxo_aplicacao.html) | **Visualizador Interativo em HTML** com layout moderno, navegação em abas, cards explicativos e diagramas Mermaid renderizados nativamente em SVG com tema escuro profissional. |

---

## 🚀 Como Visualizar o Fluxo Interativo no Navegador

Abra o arquivo [`fluxo_aplicacao.html`](fluxo_aplicacao.html) diretamente no seu navegador padrão:

* **No macOS:**
  ```bash
  open entrega/fluxo_aplicacao/fluxo_aplicacao.html
  ```

* **No Linux:**
  ```bash
  xdg-open entrega/fluxo_aplicacao/fluxo_aplicacao.html
  ```

* **No Windows (PowerShell):**
  ```powershell
  start entrega/fluxo_aplicacao/fluxo_aplicacao.html
  ```

Ou execute um servidor local na raiz do repositório:
```bash
python3 -m http.server 8000
```
E acesse: [http://localhost:8000/entrega/fluxo_aplicacao/fluxo_aplicacao.html](http://localhost:8000/entrega/fluxo_aplicacao/fluxo_aplicacao.html)

---

## 🧩 Principais Destaques da Arquitetura

1. **Propensão em vez de Veredito (RN01, RF12):** O sistema estima a propensão de desinformação sem nunca proferir conclusões binárias ("é falso" / "é verdade"), preservando a neutralidade jornalística (RNF02).
2. **Pedagogia e Pensamento Crítico (RF14):** Toda análise encerra com 3 perguntas-guia metodológicas que estimulam o leitor a avaliar a autoria, a atualidade das datas e a multiplicidade de fontes independentes.
3. **Estratégia "Base Primeiro" (Gate E1):** Consulta preventiva a 21.976 checagens de 9 agências cadastradas. Quando uma checagem aplicável é encontrada, a busca web aberta é suprimida, economizando custos e tempo de resposta.
4. **Agrupamento em Clusters de Independência (RF06, RN03):** Veículos pertencentes ao mesmo grupo de comunicação (ex.: Globo, Folha/UOL) ou matérias com texto idêntico têm seus votos agregados em um único cluster, impedindo distorções por republicação massiva (*syndication*).
5. **Decisão Bayesiana Determinística (RNF01):** O cálculo final é realizado por log-odds simétrico documentado e determinístico em Python, sem delegar o resultado final a alucinações de LLM.
6. **Análise de Estilo Paralela e Isolada (RN11):** O modelo BERTimbau calibrado (para $\ge 80$ palavras) e a identificação de gatilhos sensacionalistas funcionam em paralelo, mas **nunca afetam** o cálculo da propensão.
