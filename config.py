"""Configurações globais (valem para todas as fontes)."""
import sys
from pathlib import Path

# True quando o programa roda como .exe (PyInstaller)
EXECUTAVEL = getattr(sys, "frozen", False)

if EXECUTAVEL:
    # No .exe, __file__ aponta para uma pasta temporária. Tudo (downloads, fila, modelos,
    # accounts.py) fica na pasta onde o .exe está.
    BASE_DIR = Path(sys.executable).resolve().parent
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))  # permite ler o accounts.py ao lado do .exe
else:
    # Base = pasta onde este arquivo está; funciona mesmo rodando de outro diretório
    BASE_DIR = Path(__file__).resolve().parent

# Como o usuário manda processar a fila de novo (usado nas mensagens)
COMO_REPROCESSAR = (
    'abra o programa e escolha "Processar a fila de relatórios pendentes"'
    if EXECUTAVEL else "rode python main.py --fila"
)

# Pasta onde o navegador baixa os arquivos (depois são movidos para subpastas)
DOWNLOAD_DIR = str(BASE_DIR / "downloads")

# True = depois de baixar, gera os relatórios (com a ferramenta escolhida: Gemini ou Claude)
ENVIAR_NOTEBOOKLM = True

# False = deixa o navegador aberto ao final (comportamento anterior)
FECHAR_NAVEGADOR = False

# ---------------------------------------------------------------------------
# Ferramentas de análise: o usuário escolhe uma delas logo depois da data e da empresa
# (e também ao processar a fila). Chave interna -> nome mostrado no menu.
# ---------------------------------------------------------------------------

# Como o Claude é usado:
#   "assinatura" = pela assinatura Claude Pro/Max, com o Claude Code instalado no computador
#                  (sem custo por relatório; usa a cota da assinatura). Veja o LEIA-ME.txt.
#   "api"        = pela API da Anthropic, pago por uso (precisa de chave da API e créditos)
CLAUDE_MODO = "assinatura"

FERRAMENTAS = {
    "gemini": "Gemini (NotebookLM)",
    "claude": "Claude (assinatura)" if CLAUDE_MODO == "assinatura" else "Claude (API da Anthropic)",
}

# ---------------------------------------------------------------------------
# Relatório (vale para as duas ferramentas)
# ---------------------------------------------------------------------------
ARQUIVO_FILA = str(BASE_DIR / "fila_notebooklm.json")

# ATENÇÃO: o NotebookLM usa o NOME DO ARQUIVO como nome da fonte, e o prompt
# cita esse nome ("Novo Modelo do Relatório"). Nomeie o arquivo de acordo.
# (No Claude o modelo é enviado sempre com o título "Novo Modelo do Relatório".)
MODELO_USUARIO = Path.home() / "Documents" / "modelos_relatorio" / "modelo_relatorio.pdf"
MODELO_PADRAO = str(BASE_DIR / "modelo_relatorio.pdf")
MODELO_RELATORIO = str(MODELO_USUARIO if MODELO_USUARIO.is_file() else MODELO_PADRAO)

# Relatório final: o modelo .docx é preenchido com a resposta da ferramenta
MODELO_DOCX_USUARIO = Path.home() / "Documents" / "modelos_relatorio" / "modelo_relatorio.docx"
MODELO_DOCX_PADRAO = str(BASE_DIR / "modelo_relatorio.docx")
MODELO_DOCX = str(MODELO_DOCX_USUARIO if MODELO_DOCX_USUARIO.is_file() else MODELO_DOCX_PADRAO)

# Se algum perfil usar outro modelo: {"Nome exato do perfil": "caminho/modelo.docx"}
MODELOS_DOCX_POR_PERFIL = {}
NOME_RELATORIO = "relatorio.docx"

# True = remove marcadores de citação do NotebookLM, como [1] ou [2, 3]
REMOVER_CITACOES = True

# Só é criado se a mesclagem no .docx falhar (para não perder a resposta)
NOME_RESPOSTA = "resposta_notebooklm.txt"
# Respostas parciais guardadas enquanto o relatório não está completo (cache de retomada).
# A extensão não está em EXTENSOES_FONTE, então nunca é enviada como fonte.
EXTENSAO_PARTE = ".parte"
# Arquivos gerados pelo script: nunca são reenviados como fonte
ARQUIVOS_GERADOS = {NOME_RELATORIO, NOME_RESPOSTA}
EXTENSOES_FONTE = {".pdf", ".docx", ".txt", ".md"}

# ---------------------------------------------------------------------------
# Gemini (NotebookLM)
# ---------------------------------------------------------------------------
MAX_FONTES = 50  # limite de fontes por notebook no plano gratuito

# Resiliência com o NotebookLM (a API não oficial às vezes devolve "no answer")
CONSULTA_TENTATIVAS = 2        # quantas vezes tenta a consulta por licitação
CONSULTA_ESPERA = 30           # segundos entre uma tentativa e a seguinte
PAUSA_APOS_UPLOAD = 10         # segundos antes da 1ª consulta (indexação das fontes)
PAUSA_ENTRE_LICITACOES = 20    # segundos entre uma licitação e a próxima

# Passadas automáticas no fim da fila (1 = desligado: sem passadas extras).
# Quem falhar fica com status "erro"; rode "python main.py --fila" para tentar de novo.
MAX_PASSADAS = 1
ESPERA_ENTRE_PASSADAS = 180    # segundos entre passadas (só vale se MAX_PASSADAS > 1)

# Opcional: para a fila após N licitações seguidas sem resposta (0 = desligado).
# Útil se você descobrir que o problema é limite de uso da conta.
MAX_FALHAS_SEGUIDAS = 0

# Endereço do NotebookLM/Gemini Notebook para o "nlm". Vazio = automático.
# Se o login funcionar mas a consulta falhar com "CSRF token", tente "https://notebook.google.com".
NOTEBOOKLM_BASE_URL = ""

# ---------------------------------------------------------------------------
# Claude pela assinatura (CLAUDE_MODO = "assinatura")
# ---------------------------------------------------------------------------
# Modelo do Claude Code: "sonnet" (recomendado; gasta menos cota) ou "opus" (mais caprichado,
# gasta bem mais cota; no plano Pro pode não estar disponível no Claude Code).
CLAUDE_CODE_MODELO = "sonnet"

# Tempo máximo de cada parte do relatório (segundos)
CLAUDE_CODE_TIMEOUT = 1800

# CLAUDE_ESFORCO, CLAUDE_ENVIO_PDF, CLAUDE_TENTATIVAS e CLAUDE_ESPERA (abaixo) valem
# para os dois modos.

# ---------------------------------------------------------------------------
# Claude pela API (CLAUDE_MODO = "api")
# A chave da API fica no accounts.py:  CLAUDE = {"api_key": "sk-ant-..."}
# (ou na variável de ambiente ANTHROPIC_API_KEY).
# ---------------------------------------------------------------------------
# Modelo usado nas análises (preço por milhão de tokens: entrada / saída):
#   "claude-sonnet-5-5"  US$ 2 / US$ 10   -> recomendado: ótimo em editais e bem mais barato
#   "claude-opus-5-5"    US$ 4 / US$ 20   -> o mais caprichado, custa o dobro
CLAUDE_MODELO = "claude-sonnet-5-5"

# Esforço: "low", "medium", "high", "xhigh" ou "max".
# Mais alto = análise mais cuidadosa, porém mais lenta e cara. "medium" economiza.
CLAUDE_ESFORCO = "high"

# True = o Claude raciocina antes de responder (melhor em editais longos; gasta mais saída)
CLAUDE_PENSAMENTO = True

# Limite de tokens da resposta de cada parte (inclui o raciocínio). Se o relatório sair
# com o aviso "resposta cortada", aumente (máximo 128000).
CLAUDE_MAX_TOKENS = 64000

# Como os PDFs da licitação são enviados:
#   "texto" = o texto é extraído aqui, com a marcação [Página N] (o Claude consegue citar as
#             páginas). PDF escaneado (sem texto) vai como PDF. Custa cerca de 3 a 4x menos.
#   "pdf"   = todo PDF vai como PDF: o Claude também "vê" as páginas (tabelas, carimbos),
#             mas cada página custa bem mais.
CLAUDE_ENVIO_PDF = "texto"

# Limites da API para cada consulta (PDFs enviados como PDF contam páginas e tamanho)
CLAUDE_MAX_PAGINAS_PDF = 550   # a API aceita até 600 páginas de PDF por consulta
CLAUDE_MAX_MB_REQUISICAO = 30  # a API aceita até 32 MB por consulta

# Resiliência: a API às vezes fica sobrecarregada (erro 529) ou atinge o limite (429)
CLAUDE_TENTATIVAS = 3          # tentativas por parte do relatório (o limite da assinatura não é repetido)
CLAUDE_ESPERA = 30             # segundos de espera antes de tentar de novo (cresce a cada vez)

# US$ por milhão de tokens (entrada, saída): só para mostrar o custo estimado de cada parte.
# Gravar no cache custa 1,25x a entrada; ler do cache, 0,05x (Sonnet 5.5 e Opus 5.5).
CLAUDE_PRECOS = {
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
}
