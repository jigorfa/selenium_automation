"""
Prompts personalizados por empresa.

Para personalizar uma empresa, adicione seu nome e o prompt desejado.

Empresas não cadastradas continuam usando os prompts padrão.
"""

PROMPTS = {
    "Bioi - Farmácia de Manipulação": {
        0: """
Escreva aqui o prompt personalizado para o relatório principal.
""",
        1: """
Escreva aqui o prompt personalizado para os itens por categoria.
""",

    },

    # Exemplo para cadastrar outra empresa:
    # após a virgula copie esse trecho sem as #
    #
    # "Nome da outra empresa": {
    #     0: """
    #     Prompt personalizado do relatório principal.
    #     """,
    #     1: """
    #     Prompt personalizado dos itens por categoria.
    #     """,
    # },
}
