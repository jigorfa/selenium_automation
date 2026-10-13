"""Prompt enviado ao NotebookLM (o mesmo para todos os perfis).

O trabalho é dividido em PARTES: (título, prompt). Cada parte é uma consulta separada
e as respostas são unidas no mesmo relatório .docx. Dividir evita pedir uma resposta
enorme de uma vez, o que fazia o NotebookLM falhar ("Não foi possível gerar uma resposta").

O título vira o cabeçalho da parte no .docx; None na primeira parte (o relatório já
traz o próprio título).
"""

import os

from config import MODELO_RELATORIO

PROMPT_RELATORIO = """\
Analise cuidadosamente o edital/aviso de contratação e todos os anexos disponibilizados.

1. Extraia apenas as informações contidas nos documentos, sem respostas genéricas ou inferências externas.
2. Organize os dados no "Novo Modelo do Relatório".
3. Respeite rigorosamente a ordem das informações apresentadas nos arquivos.
4. Não invente, não complemente com dados externos, não generalize. Apenas reproduza o que está nos documentos."""

PROMPT_ITENS = """\
Analise cuidadosamente o edital/aviso de contratação e todos os anexos disponibilizados.

1. Extraia apenas as informações contidas nos documentos, sem respostas genéricas ou inferências externas.
2. Liste os itens exclusivamente pelos seus números (sem nomes) dentro das seguintes categorias:
* Manipulados
* Cannabidiol
* Injetáveis
* Oftalmológicos
3. Informe o local exato onde os medicamentos podem ser encontrados, nos documentos (pagina) conforme indicado nos documentos.
4. Respeite rigorosamente a ordem das informações apresentadas nos arquivos.
5. Não invente, não complemente com dados externos, não generalize. Apenas reproduza o que está nos documentos."""

PARTES = [
    (None, PROMPT_RELATORIO),
    ("Itens por categoria e localização", PROMPT_ITENS),
]

# ---------------------------------------------------------------------------
# Plano B: se o NotebookLM não gerar resposta para uma PARTE inteira, ela é refeita
# em pedaços menores (um prompt por seção do modelo). A chave é o índice em PARTES;
# cada pedaço é (rótulo, prompt) e as respostas são coladas na ordem.
# ---------------------------------------------------------------------------
_MODELO = os.path.basename(MODELO_RELATORIO)

_BASE = (
    "Analise cuidadosamente o edital/aviso de contratação e todos os anexos disponibilizados. "
    "Extraia apenas informações contidas nos documentos, sem inferências externas; "
    "não invente nem generalize. Se uma informação não constar nos documentos, escreva \"Não consta\". "
)
_SO = f"Use o modelo de relatório ({_MODELO}) e preencha SOMENTE a parte pedida abaixo. "

ALTERNATIVAS = {
    0: [
        (
            "Relatório de Edital (início)",
            _BASE + _SO
            + "Preencha do título \"Relatório de Edital\" até o campo \"Prazo de pagamento\" "
            "(Objeto, Itens, Valor estimado, Exige garantias, Endereço, Prazo e Forma de entrega, "
            "Prazo de pagamento). Mantenha o título e os campos exatamente como no modelo.",
        ),
        (
            "Pontos de atenção",
            _BASE + _SO
            + "Preencha a seção \"Pontos de atenção\" completa, com todos os tópicos do modelo "
            "(incluindo Rotas, licitação para licitantes pré qualificados e Presencial ou eletrônica). "
            "Mantenha o título e os tópicos exatamente como no modelo.",
        ),
        (
            "Resumo edital (1 a 6)",
            _BASE + _SO
            + "Preencha o título \"Resumo edital\" e os itens 1 a 6 (nome do órgão, número do pregão, "
            "número do processo, link do portal, data da disputa, critério de julgamento). "
            "Mantenha a numeração do modelo.",
        ),
        (
            "Resumo edital (7 a 13)",
            _BASE + _SO
            + "Preencha os itens 7 a 13 do \"Resumo edital\", com todos os subitens (a., b., i., ii.). "
            "Mantenha a numeração do modelo e NÃO repita o título nem os itens 1 a 6.",
        ),
    ],
    1: [
        (
            f"Itens: {categoria}",
            "Analise cuidadosamente o edital/aviso de contratação e todos os anexos disponibilizados. "
            "Extraia apenas informações contidas nos documentos. "
            f"Liste os itens da categoria {categoria} exclusivamente pelos seus números (sem nomes) "
            "e informe o documento e a página onde constam. "
            f"Comece a resposta com o nome da categoria em negrito. Se não houver itens, responda: **{categoria}:** Não consta.",
        )
        for categoria in ("Manipulados", "Cannabidiol", "Injetáveis", "Oftalmológicos")
    ],
}


def obter_prompts(chave=None):
    """Todos os perfis usam as mesmas partes. O parâmetro `chave` é ignorado; existe só
    porque itens antigos da fila ainda guardam "padrao"/"bioin"."""
    return PARTES


def obter_alternativas(indice):
    """Pedaços menores de uma parte (lista de (rótulo, prompt)); vazia se não houver."""
    return ALTERNATIVAS.get(indice, [])
