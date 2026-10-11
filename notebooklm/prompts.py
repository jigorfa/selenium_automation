"""Prompt enviado ao NotebookLM (o mesmo para todos os perfis).

O trabalho é dividido em PARTES: (título, prompt). Cada parte é uma consulta separada
e as respostas são unidas no mesmo relatório .docx. Dividir evita pedir uma resposta
enorme de uma vez, o que fazia o NotebookLM falhar ("Não foi possível gerar uma resposta").

O título vira o cabeçalho da parte no .docx; None na primeira parte (o relatório já
traz o próprio título).
"""

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


def obter_prompts(chave=None):
    """Todos os perfis usam as mesmas partes. O parâmetro `chave` é ignorado; existe só
    porque itens antigos da fila ainda guardam "padrao"/"bioin"."""
    return PARTES
