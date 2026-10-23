"""Processa a fila: prepara os documentos, roda os prompts, salva o relatório.

Duas ferramentas (o usuário escolhe ao rodar):
    "gemini": cria um notebook no NotebookLM, envia as fontes e consulta pelo "nlm".
    "claude": monta os documentos aqui e consulta a API do Claude.
As partes do relatório, o cache de retomada (.parte) e o .docx final são os mesmos.
"""
import glob
import json
import os
import time
from dataclasses import dataclass, field

from claude_api import assinatura
from claude_api.client import LimiteAssinatura, ParadaGeral, SemChave
from claude_api.client import consultar as consultar_api, custo_total
from claude_api.client import testar_conexao as testar_api
from claude_api.documentos import DocumentosInvalidos, montar_pacote
from config import (
    ARQUIVO_FILA,
    CLAUDE_MODO,
    COMO_REPROCESSAR,
    FERRAMENTAS,
    MAX_FALHAS_SEGUIDAS,
    ESPERA_ENTRE_PASSADAS,
    EXTENSAO_PARTE,
    MAX_FONTES,
    MAX_PASSADAS,
    MODELO_RELATORIO,
    NOME_RELATORIO,
    NOME_RESPOSTA,
    PAUSA_APOS_UPLOAD,
    PAUSA_ENTRE_LICITACOES,
)
from notebooklm.archive import coletar_arquivos, descrever_pasta, extrair_zips
from notebooklm.client import (
    adicionar_arquivo,
    consultar,
    criar_notebook,
    SemResposta,
    erro_passageiro,
    testar_conexao,
)
from notebooklm.prompts import obter_alternativas, obter_prompts
from notebooklm.queue import carregar_fila, salvar_fila
from notebooklm.report import gerar_relatorio, modelo_para


def extrair_resposta(saida):
    try:
        dados = json.loads(saida)
        if isinstance(dados, dict):
            resposta = dados.get("answer") or (dados.get("value") or {}).get("answer")
            if resposta:
                return resposta
    except (json.JSONDecodeError, AttributeError):
        pass
    return saida


class SemArquivos(RuntimeError):
    """A pasta não tem nenhum arquivo utilizável (vazia, só arquivos de 0 bytes ou de tipo
    não aceito). Em geral é falha de DOWNLOAD: vale baixar de novo (ver main.py)."""


class ParteIncompleta(RuntimeError):
    """Alguns pedaços da parte ficaram sem resposta; `texto` guarda o que veio."""

    def __init__(self, texto, faltam, n):
        super().__init__(
            f"{faltam} pedaço(s) da parte {n + 1} ficaram sem resposta (no answer); "
            f"Para completar, {COMO_REPROCESSAR}."
        )
        self.texto = texto


def _ler(arq):
    with open(arq, encoding="utf-8") as f:
        return f.read()


def _gravar(arq, texto):
    with open(arq, "w", encoding="utf-8") as f:
        f.write(texto)


def _consultar_parte(notebook_id, pasta, n, prompt):
    """Consulta uma parte. Se o NotebookLM não gerar resposta, refaz em pedaços menores
    (cada pedaço respondido fica em cache, então uma nova rodada só refaz o que faltou)."""
    pedacos = obter_alternativas(n)
    cache = lambda k: os.path.join(pasta, f"parte_{n + 1}_{k + 1}{EXTENSAO_PARTE}")
    ja_dividida = any(os.path.exists(cache(k)) for k in range(len(pedacos)))

    if not ja_dividida:
        try:
            return extrair_resposta(consultar(notebook_id, prompt))
        except SemResposta:
            if not pedacos:
                raise
            print(f"    Sem resposta para a parte inteira; refazendo em {len(pedacos)} pedaços menores...")

    textos, faltam = [], 0
    for k, (rotulo, sub) in enumerate(pedacos):
        if os.path.exists(cache(k)):
            textos.append(_ler(cache(k)))
            print(f"      Pedaço {k + 1}/{len(pedacos)} ({rotulo}) já respondido; reaproveitando.")
            continue
        time.sleep(PAUSA_APOS_UPLOAD)
        print(f"      Pedaço {k + 1}/{len(pedacos)}: {rotulo}")
        try:
            texto = extrair_resposta(consultar(notebook_id, sub))
        except SemResposta:
            faltam += 1
            print("        sem resposta")
            textos.append(f"**[NÃO GERADO: {rotulo} - o NotebookLM não respondeu.]**")
            continue
        _gravar(cache(k), texto)
        textos.append(texto)

    resultado = "\n\n".join(textos)
    if faltam == len(pedacos):
        raise SemResposta("The notebook returned no answer (todos os pedaços).")
    if faltam:
        raise ParteIncompleta(resultado, faltam, n)
    return resultado


def _preparar_gemini(fila, pasta, job, arquivos):
    """Cria o notebook (uma vez) e envia o que falta. Devolve a função que consulta uma parte."""
    limite = MAX_FONTES - 1  # 1 vaga é do modelo de relatório
    if len(arquivos) > limite:
        print(f"    Aviso: {len(arquivos)} arquivos; enviando só os {limite} primeiros.")
        arquivos = arquivos[:limite]

    if not job.get("notebook_id"):
        # Itens antigos não têm "data": recupera da pasta (.../<fonte>/<data>/<licitação>)
        data = job.get("data") or os.path.basename(os.path.dirname(pasta)).replace("-", "/")
        job["notebook_id"] = criar_notebook(f"{job['titulo'][:80]} ({data})")
        salvar_fila(fila)
        print(f"    Notebook criado: {job['notebook_id']}")

    notebook_id = job["notebook_id"]
    # "fontes" é o nome antigo do campo; mantido só para não reenviar itens antigos
    enviados = job.setdefault("arquivos_enviados", list(job.get("fontes", [])))

    for arquivo in [MODELO_RELATORIO] + arquivos:
        if arquivo in enviados:
            continue
        print(f"    Enviando: {os.path.basename(arquivo)}")
        adicionar_arquivo(notebook_id, arquivo)
        enviados.append(arquivo)
        salvar_fila(fila)

    time.sleep(PAUSA_APOS_UPLOAD)  # dá tempo para o NotebookLM terminar de indexar
    return lambda n, prompt: _consultar_parte(notebook_id, pasta, n, prompt)


def _preparar_claude(pasta, arquivos):
    """Monta os documentos (texto/PDF) uma vez. Devolve a função que consulta uma parte."""
    print("    Preparando os documentos para o Claude...")
    try:
        pacote = montar_pacote(pasta, arquivos, MODELO_RELATORIO)
    except DocumentosInvalidos as erro:  # ex.: PDFs corrompidos no download: vale baixar de novo
        raise SemArquivos(str(erro)) from erro
    print(f"    {pacote.resumo()}")
    if CLAUDE_MODO == "assinatura":
        sessao = assinatura.Sessao(pacote, pasta)
        return lambda n, prompt: sessao.consultar(prompt)
    return lambda n, prompt: consultar_api(pacote.blocos, prompt)


def processar_job(fila, pasta, job, ferramenta="gemini"):
    nome = FERRAMENTAS[ferramenta]
    print(f"\n[{nome}] {os.path.basename(pasta)}")

    extrair_zips(pasta)

    arquivos = coletar_arquivos(pasta)
    if not arquivos:
        raise SemArquivos(
            "Nenhum arquivo compatível (PDF/DOCX/TXT/MD) na pasta. "
            + descrever_pasta(pasta)
        )

    if ferramenta == "claude":
        consultar_parte = _preparar_claude(pasta, arquivos)
    else:
        consultar_parte = _preparar_gemini(fila, pasta, job, arquivos)

    # Itens antigos (sem "prompt") eram todos do Bioin
    partes = obter_prompts(job.get("prompt", "bioin"))
    destino = os.path.join(pasta, NOME_RELATORIO)
    modelo = modelo_para(job.get("perfil"))
    respostas = {}

    for n, (_, prompt) in enumerate(partes):
        arq = os.path.join(pasta, f"parte_{n + 1}{EXTENSAO_PARTE}")

        if os.path.exists(arq):  # respondida numa tentativa anterior: não gasta consulta
            respostas[n] = _ler(arq)
            print(f"    Parte {n + 1}/{len(partes)} já respondida; reaproveitando.")
            continue

        if n > 0 and ferramenta == "gemini":
            time.sleep(PAUSA_APOS_UPLOAD)
        print(f"    Executando o prompt, parte {n + 1}/{len(partes)} (pode demorar alguns minutos)...")
        try:
            respostas[n] = consultar_parte(n, prompt)
        except ParteIncompleta as erro:
            respostas[n] = erro.texto  # relatório parcial, com aviso nos pedaços que faltam
            _salvar_relatorio(partes, respostas, destino, modelo, nome)
            raise
        except Exception:
            if respostas:  # não perde o que já veio: grava o relatório parcial
                _salvar_relatorio(partes, respostas, destino, modelo, nome)
            raise

        _gravar(arq, respostas[n])

    _salvar_relatorio(partes, respostas, destino, modelo, nome)
    # relatório completo: o cache de retomada (parte_*.parte) não é mais preciso
    for arq in glob.glob(os.path.join(glob.escape(pasta), f"parte_*{EXTENSAO_PARTE}")):
        os.remove(arq)


def montar_markdown(partes, respostas, nome_ferramenta="NotebookLM"):
    """Une as respostas das partes; parte sem resposta vira um aviso visível no relatório."""
    blocos = []
    for n, (titulo, _) in enumerate(partes):
        if n > 0 and titulo:
            blocos.append(f"## {titulo}")
        blocos.append(
            respostas.get(n)
            or f"**[NÃO GERADO: {titulo or 'relatório'} - o {nome_ferramenta} não respondeu. "
               f"Para completar, {COMO_REPROCESSAR}.]**"
        )
    return "\n\n".join(blocos)


def _salvar_relatorio(partes, respostas, destino, modelo, nome_ferramenta="NotebookLM"):
    markdown = montar_markdown(partes, respostas, nome_ferramenta)
    try:
        gerar_relatorio(markdown, destino, modelo)
        faltam = len(partes) - len(respostas)
        aviso = f" (faltam {faltam} parte(s))" if faltam else ""
        print(f"    Relatório salvo em: {destino}{aviso}")
    except Exception as erro:
        # Nunca perde a resposta (que leva minutos para gerar): guarda o texto bruto
        bruto = os.path.join(os.path.dirname(destino), NOME_RESPOSTA)
        with open(bruto, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"    AVISO: não consegui montar o .docx ({type(erro).__name__}: {erro})")
        print(f"    Resposta bruta salva em: {bruto}")


def _falhas_passageiras(fila):
    """Pastas cujo último erro foi 'sem resposta'/limite/timeout (vale tentar de novo)."""
    return [
        p for p, j in fila.items()
        if j.get("status") == "erro" and not j.get("sem_arquivos")
        and erro_passageiro(RuntimeError(j.get("erro") or ""))
    ]


def _rodar_passada(fila, pendentes, ferramenta="gemini"):
    falhas_seguidas = 0
    consultou = True  # False se a licitação anterior falhou antes de falar com a ferramenta
    for numero, (pasta, job) in enumerate(pendentes):
        if numero > 0 and consultou and ferramenta == "gemini":
            time.sleep(PAUSA_ENTRE_LICITACOES)  # evita consultas em sequência rápida
        job["ferramenta"] = ferramenta  # registra qual ferramenta gerou (ou tentou gerar)
        try:
            processar_job(fila, pasta, job, ferramenta)
            job["status"] = "concluido"
            job["erro"] = None
            job.pop("sem_arquivos", None)
            falhas_seguidas = 0
            consultou = True
        except ParadaGeral as erro:
            # Sem login/chave ou limite da assinatura: todas as próximas falhariam igual
            job["status"] = "erro"
            job["erro"] = str(erro)
            salvar_fila(fila)
            print(f"    ERRO: {erro}")
            raise
        except Exception as erro:
            job["status"] = "erro"
            job["erro"] = str(erro)
            job["sem_arquivos"] = isinstance(erro, SemArquivos)
            consultou = not isinstance(erro, SemArquivos)
            print(f"    ERRO: {erro}")
            if ferramenta == "gemini":
                print(f"    (notebook: {job.get('notebook_id')})")
            # Só conta "sem resposta/limite"; erro de arquivo, por exemplo, não conta
            falhas_seguidas = falhas_seguidas + 1 if erro_passageiro(erro) else 0
        salvar_fila(fila)

        if MAX_FALHAS_SEGUIDAS and falhas_seguidas >= MAX_FALHAS_SEGUIDAS:
            print(f"\nParei: {falhas_seguidas} licitações seguidas sem resposta (MAX_FALHAS_SEGUIDAS).")
            return False
    return True


@dataclass
class ResultadoFila:
    """O que aconteceu ao processar a fila (quem chama decide o que perguntar ao usuário)."""
    # "sem_modelo" | "sem_login" (NotebookLM) | "sem_chave" | "sem_conexao" | "limite" (Claude)
    # | None (rodou normalmente)
    motivo_parada: str | None = None
    detalhe: str = ""                  # mensagem do problema, quando houve parada
    concluidos: int = 0
    total: int = 0
    falhas: list = field(default_factory=list)  # [(nome da licitação, mensagem de erro)]
    sem_arquivos: list = field(default_factory=list)  # pastas sem arquivo utilizável, ainda não baixadas de novo


def _resultado(fila, motivo=None, detalhe=""):
    return ResultadoFila(
        motivo_parada=motivo,
        detalhe=detalhe,
        concluidos=sum(1 for j in fila.values() if j.get("status") == "concluido"),
        total=len(fila),
        falhas=[
            (os.path.basename(p), j.get("erro") or "não processada")
            for p, j in fila.items() if j.get("status") != "concluido"
        ],
        sem_arquivos=[
            p for p, j in fila.items()
            if j.get("status") == "erro" and j.get("sem_arquivos") and not j.get("redownload_tentado")
        ],
    )


def _testar_ferramenta(fila, ferramenta):
    """Confere o acesso antes de começar. Devolve um ResultadoFila de parada, ou None se ok."""
    if ferramenta == "claude":
        try:
            (assinatura.testar_conexao if CLAUDE_MODO == "assinatura" else testar_api)()
        except SemChave as erro:
            print(erro)
            return _resultado(fila, "sem_chave", str(erro))
        except Exception as erro:  # rede, modelo errado... (a mensagem já diz "Claude: ...")
            print(erro)
            return _resultado(fila, "sem_conexao", str(erro))
        return None

    try:
        testar_conexao()
    except Exception as erro:
        print(f"Não consegui falar com o NotebookLM: {erro}")
        return _resultado(fila, "sem_login", str(erro))
    return None


def processar_fila(somente=None, ferramenta="gemini"):
    """Processa a fila com a `ferramenta` ("gemini" ou "claude").
    `somente` (conjunto de pastas) limita o trabalho a essas licitações."""
    fila = carregar_fila()
    pendentes = [
        (p, j) for p, j in fila.items()
        if j.get("status") != "concluido" and (somente is None or p in somente)
    ]

    print(f"\n===== FILA ({FERRAMENTAS[ferramenta]}): {len(pendentes)} pendente(s) =====")
    if not pendentes:
        return _resultado(fila)

    if not os.path.exists(MODELO_RELATORIO):
        detalhe = f"Modelo de relatório não encontrado: {MODELO_RELATORIO}"
        print(detalhe)
        print("Coloque o arquivo modelo_relatorio.pdf nessa pasta (ou ajuste MODELO_RELATORIO em config.py).")
        return _resultado(fila, "sem_modelo", detalhe)

    parada = _testar_ferramenta(fila, ferramenta)
    if parada:
        return parada

    custo_antes = custo_total()
    for passada in range(1, MAX_PASSADAS + 1):
        if passada > 1:
            pendentes = [(p, fila[p]) for p in _falhas_passageiras(fila) if somente is None or p in somente]
            print(f"\n===== PASSADA {passada}/{MAX_PASSADAS}: {len(pendentes)} para tentar de novo =====")

        try:
            completou = _rodar_passada(fila, pendentes, ferramenta)
        except ParadaGeral as erro:
            motivo = "limite" if isinstance(erro, LimiteAssinatura) else "sem_chave"
            return _resultado(fila, motivo, str(erro))
        restantes = [p for p in _falhas_passageiras(fila) if somente is None or p in somente]

        if not completou or not restantes or passada == MAX_PASSADAS:
            break

        print(f"\n{len(restantes)} sem resposta. Nova passada em {ESPERA_ENTRE_PASSADAS // 60} min...")
        time.sleep(ESPERA_ENTRE_PASSADAS)

    resultado = _resultado(fila)
    print(f"\nFila: {resultado.concluidos}/{resultado.total} concluído(s). Estado em: {ARQUIVO_FILA}")
    if ferramenta == "claude" and custo_total() > custo_antes:
        print(f"Custo estimado do Claude nesta rodada: US$ {custo_total() - custo_antes:.2f}")
    return resultado
