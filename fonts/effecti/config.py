"""Configurações exclusivas do Effecti."""

NOME_FONTE = "effecti"

URL_SISTEMA = "https://minha.effecti.com.br/#/avisos-configuracoes-perfis-v2"

# Nomes exatamente como aparecem na coluna "Nome" da tabela de perfis
PERFIS = [
    "AF Temoteo",
    "Bioin - Farmácia de Manipulação",
    "Irmãos Costa & Licitações",
    "Layane Cristine",
    "Link of Americas",
    "Loja do Militar",
    "LP Soluções em Licitações",
    "Migox - Gases",
    "Tech Master",
]

PERFIL_BIOIN = "Bioin - Farmácia de Manipulação"

# Nome da pasta de cada empresa em downloads/effecti/<data>/<empresa>/<licitação>/.
# Perfil que não estiver aqui usa o próprio nome do perfil. Exemplo para encurtar:
#   PASTA_POR_PERFIL = {"Bioin - Farmácia de Manipulação": "Bioin"}
# (nomes mais curtos também ajudam a não estourar o limite de 260 caracteres do Windows)
PASTA_POR_PERFIL = {}

# Qual prompt (chave de notebooklm/prompts.py) usar para cada perfil.
# Perfil que não estiver aqui usa "padrao".
PROMPT_POR_PERFIL = {}

# Portais que o script ainda não trata: a licitação é pulada.
# Deixe a lista vazia se todos passaram a ser baixados pelo clipe.
PORTAIS_ESPECIAIS = []

SELETOR_CLIPE = 'a[title="Anexos da licitação"]'
SELETOR_LINKS_MODAL = "#md-edital-anexo a[href]"

# Tempo máximo (segundos) para o modal de anexos abrir
TIMEOUT_MODAL = 15

# True = processa só o primeiro favorito (útil para testes)
SO_PRIMEIRO_FAVORITO = False
