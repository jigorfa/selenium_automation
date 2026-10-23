"""Acesso ao Claude pela API oficial da Anthropic (biblioteca "anthropic").

A chave da API vem da variável de ambiente ANTHROPIC_API_KEY ou do accounts.py:
    CLAUDE = {"api_key": "sk-ant-..."}

Cada licitação faz uma consulta por parte do relatório (as mesmas partes do Gemini, em
notebooklm/prompts.py). Os documentos vão sempre iguais e na frente, com cache: a partir
da 2ª parte, eles são lidos do cache e custam cerca de 5% do preço normal.
"""
import os
import time

from config import (
    CLAUDE_ESFORCO,
    CLAUDE_ESPERA,
    CLAUDE_MAX_TOKENS,
    CLAUDE_MODELO,
    CLAUDE_PENSAMENTO,
    CLAUDE_PRECOS,
    CLAUDE_TENTATIVAS,
)

SISTEMA = """\
Você é um analista especializado em licitações públicas brasileiras. Você recebe:
- o documento "Novo Modelo do Relatório": é o MODELO a ser preenchido (estrutura, títulos, \
rótulos e numeração). Ele NÃO é documento da licitação e nada dele deve ser usado como dado;
- os documentos da licitação (edital, termo de referência, anexos, planilhas etc.). Nos textos \
extraídos de PDF, a marcação [Página N] indica o início da página N do arquivo original.

Regras de conteúdo:
1. Use somente informações que constam nos documentos da licitação. Não invente, não use \
conhecimento externo, não generalize nem suponha. Se a informação não constar, escreva "Não consta".
2. Seja específico: números, prazos, valores, percentuais e datas exatamente como nos documentos.
3. Se documentos divergirem entre si, informe as versões e em qual documento está cada uma.
4. Ao indicar onde algo está, cite o nome do arquivo e a página (ex.: "Edital.pdf, pág. 12"), \
usando o número das marcações [Página N].
5. Escreva em português do Brasil.

Regras de formato (sua resposta é convertida automaticamente em um documento Word):
- Responda direto com o conteúdo pedido: sem introdução, sem comentários finais, sem perguntas \
nem ofertas de ajuda, sem emojis.
- Markdown simples. Rótulos dos campos em **negrito** seguidos do conteúdo na mesma linha \
(ex.: **Objeto:** ...). Cada título do modelo sozinho na sua linha, escrito como no modelo.
- Listas: "- " para marcadores; "1.", "a.", "i." para listas numeradas, como no modelo. \
Subitens com 4 espaços de recuo por nível.
- Não use blocos de código, não escape caracteres (escreva R$, não R\\$) e não use marcadores \
de citação como [1].
- Use tabela Markdown só quando for realmente uma tabela de dados.
"""

PRECO_GRAVAR_CACHE = 1.25  # x preço de entrada
PRECO_LER_CACHE = 0.05     # x preço de entrada (Sonnet 5.5 e Opus 5.5)

_cliente = None
_custo_total = 0.0


class ErroClaude(RuntimeError):
    """Falha ao usar o Claude. `passageiro` = vale tentar de novo mais tarde.

    As mensagens passageiras contêm "temporariamente", "rate limit" ou "timeout" de
    propósito: é assim que o resto do programa (que guarda só o texto na fila)
    reconhece que vale tentar de novo."""

    def __init__(self, mensagem, passageiro=False):
        super().__init__(mensagem)
        self.passageiro = passageiro


class ParadaGeral(ErroClaude):
    """Falha que vale para todas as licitações: a fila para em vez de insistir nas próximas."""


class SemChave(ParadaGeral):
    """Sem chave da API / sem login na assinatura: nada funciona até o usuário corrigir."""


class LimiteAssinatura(ParadaGeral):
    """O limite de uso da assinatura (Pro/Max) acabou; ele renova sozinho depois de algumas horas."""

    def __init__(self, mensagem):
        super().__init__(mensagem, passageiro=True)


def _milhar(n):
    return f"{n:,}".replace(",", ".")


def _ler_chave():
    chave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if chave:
        return chave
    try:
        from accounts import CLAUDE
    except ImportError:  # sem accounts.py, ou accounts.py sem a parte CLAUDE
        return ""
    return str((CLAUDE or {}).get("api_key") or "").strip()


def _obter_cliente():
    global _cliente
    if _cliente is not None:
        return _cliente

    try:
        import anthropic
    except ImportError:
        raise ErroClaude("A biblioteca do Claude não está instalada. Rode: pip install anthropic")

    chave = _ler_chave()
    if not chave or not chave.startswith("sk-ant-"):
        raise SemChave(
            "Chave da API do Claude não configurada. No accounts.py, preencha "
            'CLAUDE = {"api_key": "sk-ant-..."} (veja accounts.exemplo.py e o LEIA-ME.txt).'
        )

    # A biblioteca já repete sozinha 2x erros de rede/sobrecarga, com espera crescente
    _cliente = anthropic.Anthropic(api_key=chave, max_retries=2)
    return _cliente


def _tipo_erro_corpo(erro):
    """Tipo do erro informado pela API no corpo, ex.: "overloaded_error"."""
    corpo = getattr(erro, "body", None)
    if isinstance(corpo, dict):
        detalhe = corpo.get("error") if isinstance(corpo.get("error"), dict) else corpo
        return str(detalhe.get("type") or "")
    return ""


def _mensagem_api(erro):
    corpo = getattr(erro, "body", None)
    if isinstance(corpo, dict) and isinstance(corpo.get("error"), dict):
        return str(corpo["error"].get("message") or erro)
    return str(getattr(erro, "message", None) or erro)


def traduzir_erro(erro):
    """Converte um erro da biblioteca anthropic em ErroClaude com mensagem em português."""
    if isinstance(erro, ErroClaude):
        return erro

    import anthropic

    tipo = _tipo_erro_corpo(erro)
    mensagem = _mensagem_api(erro)[:300]

    if isinstance(erro, anthropic.APITimeoutError):
        return ErroClaude("Claude: a consulta demorou demais e foi interrompida (timeout). "
                          "Pode ser a internet ou a API lenta.", passageiro=True)
    if isinstance(erro, anthropic.APIConnectionError):
        return ErroClaude("Claude: sem conexão com a API, temporariamente. Verifique a internet.",
                          passageiro=True)
    if not isinstance(erro, anthropic.APIStatusError):
        return ErroClaude(f"Claude: erro inesperado ({type(erro).__name__}: {erro})")

    status = erro.status_code
    if status == 401 or tipo == "authentication_error":
        return SemChave("Claude: a chave da API foi recusada (authentication_error). "
                        "Confira a chave no accounts.py; ela pode ter sido revogada ou expirado.")
    if status == 403 or tipo == "permission_error":
        return SemChave(f"Claude: a chave da API não tem permissão para isso (permission_error): {mensagem}")
    if status == 404 or tipo == "not_found_error":
        return ErroClaude(f"Claude: o modelo '{CLAUDE_MODELO}' não foi encontrado. "
                          "Confira CLAUDE_MODELO no config.py.")
    if status == 413 or tipo == "request_too_large":
        return ErroClaude("Claude: os documentos passam do tamanho máximo de uma consulta (32 MB). "
                          'Use CLAUDE_ENVIO_PDF = "texto" no config.py.')
    if status == 429 or tipo == "rate_limit_error":
        return ErroClaude("Claude: limite de uso da API atingido (rate limit). "
                          "Espere alguns minutos e tente de novo.", passageiro=True)
    if status == 529 or status >= 500 or tipo in ("overloaded_error", "api_error"):
        return ErroClaude(f"Claude: a API está sobrecarregada ou indisponível temporariamente "
                          f"({tipo or status}).", passageiro=True)

    baixo = mensagem.lower()
    if "credit balance" in baixo:
        return ErroClaude("Claude: a conta da API está sem créditos (credit balance is too low). "
                          "Adicione créditos no Console do Claude (platform.claude.com), em Billing.")
    if "prompt is too long" in baixo or ("context" in baixo and "exceed" in baixo):
        return ErroClaude("Claude: os documentos desta licitação passam do tamanho máximo de uma "
                          f"consulta ({mensagem}).")
    if "pdf" in baixo:
        return ErroClaude(f"Claude: a API não conseguiu ler um dos PDFs ({mensagem}). "
                          'Tente CLAUDE_ENVIO_PDF = "texto" no config.py.')
    return ErroClaude(f"Claude: a API recusou o pedido ({status}): {mensagem}")


def testar_conexao():
    """Confere a chave e o modelo antes de começar a fila (não gasta créditos)."""
    cliente = _obter_cliente()
    try:
        cliente.models.retrieve(CLAUDE_MODELO)
    except Exception as erro:
        raise traduzir_erro(erro) from erro


def _custo(uso):
    precos = CLAUDE_PRECOS.get(CLAUDE_MODELO)
    if not precos:
        return None
    entrada, saida = precos
    return ((uso.input_tokens
             + (uso.cache_creation_input_tokens or 0) * PRECO_GRAVAR_CACHE
             + (uso.cache_read_input_tokens or 0) * PRECO_LER_CACHE) * entrada
            + uso.output_tokens * saida) / 1_000_000


def _mostrar_uso(uso, segundos):
    global _custo_total
    lidos = uso.cache_read_input_tokens or 0
    entrada = uso.input_tokens + (uso.cache_creation_input_tokens or 0) + lidos
    custo = _custo(uso)
    texto = (f"      {segundos // 60:.0f}min{segundos % 60:02.0f}s | tokens: {_milhar(entrada)} de entrada"
             + (f" ({_milhar(lidos)} do cache)" if lidos else "")
             + f", {_milhar(uso.output_tokens)} de saída")
    if custo is not None:
        _custo_total += custo
        texto += f" | custo estimado: US$ {custo:.2f}"
    print(texto)


def custo_total():
    """Soma do custo estimado das consultas feitas nesta execução (US$)."""
    return _custo_total


def _com_cache(blocos):
    """Marca o último documento para cache: as próximas partes leem tudo do cache."""
    ultimo = dict(blocos[-1])
    ultimo["cache_control"] = {"type": "ephemeral"}
    return list(blocos[:-1]) + [ultimo]


def _consulta_unica(blocos, prompt):
    cliente = _obter_cliente()
    parametros = {
        "model": CLAUDE_MODELO,
        "max_tokens": CLAUDE_MAX_TOKENS,
        "system": SISTEMA,
        "messages": [{
            "role": "user",
            "content": _com_cache(blocos) + [{"type": "text", "text": prompt}],
        }],
    }
    if CLAUDE_PENSAMENTO:
        parametros["thinking"] = {"type": "adaptive"}
    if CLAUDE_ESFORCO:
        parametros["output_config"] = {"effort": CLAUDE_ESFORCO}

    inicio = ultimo_aviso = time.time()
    escritos = 0
    # Streaming: respostas longas levam minutos, e assim a conexão não fica parada
    with cliente.messages.stream(**parametros) as fluxo:
        for evento in fluxo:
            if evento.type == "content_block_delta" and evento.delta.type == "text_delta":
                escritos += len(evento.delta.text)
            agora = time.time()
            if agora - ultimo_aviso >= 20:
                ultimo_aviso = agora
                fase = f"escrevendo ({_milhar(escritos)} caracteres)" if escritos else "analisando"
                print(f"      ... {fase}, {int(agora - inicio)}s")
        final = fluxo.get_final_message()

    _mostrar_uso(final.usage, time.time() - inicio)

    texto = "".join(b.text for b in final.content if b.type == "text").strip()
    if final.stop_reason == "refusal":
        raise ErroClaude("Claude: o modelo se recusou a responder esta parte (refusal).")
    if final.stop_reason in ("max_tokens", "model_context_window_exceeded"):
        if not texto:
            raise ErroClaude("Claude: a resposta acabou antes de começar o texto (limite de "
                             "tamanho). Aumente CLAUDE_MAX_TOKENS no config.py.")
        texto += ("\n\n**[ATENÇÃO: a resposta do Claude foi cortada por limite de tamanho. "
                  "Aumente CLAUDE_MAX_TOKENS no config.py e gere este relatório de novo.]**")
    if not texto:
        raise ErroClaude("Claude: a resposta veio vazia, temporariamente.", passageiro=True)
    return texto


def consultar(blocos, prompt):
    """Faz a consulta. Sobrecarga, limite e rede são repetidos com espera crescente."""
    for tentativa in range(1, CLAUDE_TENTATIVAS + 1):
        try:
            return _consulta_unica(blocos, prompt)
        except Exception as erro:
            traduzido = traduzir_erro(erro)
            if not traduzido.passageiro or tentativa == CLAUDE_TENTATIVAS:
                raise traduzido from erro
            espera = CLAUDE_ESPERA * tentativa
            print(f"    {traduzido}")
            print(f"    Nova tentativa ({tentativa + 1}/{CLAUDE_TENTATIVAS}) em {espera}s...")
            time.sleep(espera)
