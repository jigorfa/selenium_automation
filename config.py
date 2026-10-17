"""Configurações globais (valem para todas as fontes)."""
from pathlib import Path

# Base = pasta onde este arquivo está; funciona mesmo rodando de outro diretório
BASE_DIR = Path(__file__).resolve().parent

# Pasta onde o navegador baixa os arquivos (depois são movidos para subpastas)
DOWNLOAD_DIR = str(BASE_DIR / "downloads")

# True = depois de baixar, envia as licitações para o NotebookLM
ENVIAR_NOTEBOOKLM = True

# False = deixa o navegador aberto ao final (comportamento anterior)
FECHAR_NAVEGADOR = False

# ---------------------------------------------------------------------------
# NotebookLM
# ---------------------------------------------------------------------------
ARQUIVO_FILA = str(BASE_DIR / "fila_notebooklm.json")

# ATENÇÃO: o NotebookLM usa o NOME DO ARQUIVO como nome da fonte, e o prompt
# cita esse nome ("Novo Modelo do Relatório"). Nomeie o arquivo de acordo.

MODELO_USUARIO = Path.home() / "Documents" / "modelos_relatorio" / "modelo_relatorio.pdf"
MODELO_PADRAO = str(BASE_DIR / "modelo_relatorio.pdf")
MODELO_RELATORIO = str(MODELO_USUARIO if MODELO_USUARIO.is_file() else MODELO_PADRAO)

# Relatório final: o modelo .docx é preenchido com a resposta do NotebookLM

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
# A extensão não está em EXTENSOES_FONTE, então nunca é enviada ao NotebookLM.
EXTENSAO_PARTE = ".parte"
# Arquivos gerados pelo script: nunca são reenviados ao NotebookLM como fonte
ARQUIVOS_GERADOS = {NOME_RELATORIO, NOME_RESPOSTA}
EXTENSOES_FONTE = {".pdf", ".docx", ".txt", ".md"}
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
