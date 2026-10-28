"""Prompts padrão e prompts personalizados por empresa."""

import json
import os

from config import BASE_DIR, MODELO_RELATORIO
from prompts_personalizados import PROMPTS


ARQUIVO_PROMPTS = BASE_DIR / "prompts_empresas.json"


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


# Prompts padrão: mantidos para empresas sem personalização.
PARTES = [
    (None, PROMPT_RELATORIO),
    ("Itens por categoria e localização", PROMPT_ITENS),
]


_MODELO = os.path.basename(MODELO_RELATORIO)

_BASE = (
    "Analise cuidadosamente o edital/aviso de contratação e todos os anexos disponibilizados. "
    "Extraia apenas informações contidas nos documentos, sem inferências externas; "
    "não invente nem generalize. Se uma informação não constar nos documentos, escreva \"Não consta\". "
)

_SO = f"Use o modelo de relatório ({_MODELO}) e preencha SOMENTE a parte pedida abaixo. "


# Prompts alternativos padrão, usados quando uma consulta inteira falha.
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
            f"Comece a resposta com o nome da categoria em negrito. "
            f"Se não houver itens, responda: **{categoria}:** Não consta.",
        )
        for categoria in ("Manipulados", "Cannabidiol", "Injetáveis", "Oftalmológicos")
    ],
}


def _carregar_configuracao():
    """Lê os prompts personalizados. Se o arquivo não existir ou estiver inválido,
    mantém o funcionamento com os prompts padrão."""
    if not ARQUIVO_PROMPTS.is_file():
        return {}

    try:
        with open(ARQUIVO_PROMPTS, "r", encoding="utf-8-sig") as arquivo:
            dados = json.load(arquivo)
    except (OSError, json.JSONDecodeError) as erro:
        print(
            f"Aviso: não foi possível ler {ARQUIVO_PROMPTS.name}: {erro}. "
            "Serão usados os prompts padrão."
        )
        return {}

    if not isinstance(dados, dict):
        print("Aviso: prompts_empresas.json deve conter um objeto JSON. Usando prompts padrão.")
        return {}

    empresas = dados.get("empresas", {})
    if not isinstance(empresas, dict):
        print("Aviso: a propriedade 'empresas' deve ser um objeto. Usando prompts padrão.")
        return {}

    return empresas


def _prompts_da_empresa(perfil):
    """Devolve os prompts personalizados para o perfil informado."""
    if not perfil:
        return {}

    empresas = _carregar_configuracao()
    configuracao = empresas.get(perfil, {})

    if not isinstance(configuracao, dict):
        return {}

    partes = configuracao.get("partes", {})
    return partes if isinstance(partes, dict) else {}


def obter_prompts(chave=None, perfil=None):
    """Usa prompts personalizados quando existem; caso contrário, usa os padrões."""
    personalizados = PROMPTS.get(perfil, {})
    resultado = []

    for indice, (titulo, prompt_padrao) in enumerate(PARTES):
        prompt = personalizados.get(indice, prompt_padrao)
        resultado.append((titulo, prompt))

    return resultado

def obter_alternativas(indice, perfil=None):
    """Retorna os prompts alternativos padrão, exceto quando a parte foi personalizada.

    Não aplica prompts alternativos genéricos a uma parte personalizada, pois isso
    poderia substituir as instruções específicas da empresa.
    """
    partes_personalizadas = _prompts_da_empresa(perfil)
    prompt_personalizado = partes_personalizadas.get(str(indice))

    if isinstance(prompt_personalizado, str) and prompt_personalizado.strip():
        return []

    return ALTERNATIVAS.get(indice, [])
