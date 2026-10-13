"""Processa a fila: cria o notebook, envia as fontes, roda o prompt, salva a resposta."""
import glob
import json
import os
import time
from dataclasses import dataclass, field

from config import (
    ARQUIVO_FILA,
    COMO_REPROCESSAR,
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


def processar_job(fila, pasta, job):
    print(f"\n[NotebookLM] {os.path.basename(pasta)}")

    extrair_zips(pasta)

    arquivos = coletar_arquivos(pasta)
    if not arquivos:
        raise RuntimeError(
            "Nenhum arquivo compatível (PDF/DOCX/TXT/MD) na pasta. "
            + descrever_pasta(pasta)
        )

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

        if n > 0:
            time.sleep(PAUSA_APOS_UPLOAD)
        print(f"    Executando o prompt, parte {n + 1}/{len(partes)} (pode demorar alguns minutos)...")
        try:
            respostas[n] = _consultar_parte(notebook_id, pasta, n, prompt)
        except ParteIncompleta as erro:
            respostas[n] = erro.texto  # relatório parcial, com aviso nos pedaços que faltam
            _salvar_relatorio(partes, respostas, destino, modelo)
            raise
        except Exception:
            if respostas:  # não perde o que já veio: grava o relatório parcial
                _salvar_relatorio(partes, respostas, destino, modelo)
            raise

        _gravar(arq, respostas[n])

    _salvar_relatorio(partes, respostas, destino, modelo)
    # relatório completo: o cache de retomada (parte_*.parte) não é mais preciso
    for arq in glob.glob(os.path.join(glob.escape(pasta), f"parte_*{EXTENSAO_PARTE}")):
        os.remove(arq)


def montar_markdown(partes, respostas):
    """Une as respostas das partes; parte sem resposta vira um aviso visível no relatório."""
    blocos = []
    for n, (titulo, _) in enumerate(partes):
        if n > 0 and titulo:
            blocos.append(f"## {titulo}")
        blocos.append(
            respostas.get(n)
            or f"**[NÃO GERADO: {titulo or 'relatório'} - o NotebookLM não respondeu. "
               f"Para completar, {COMO_REPROCESSAR}.]**"
        )
    return "\n\n".join(blocos)


def _salvar_relatorio(partes, respostas, destino, modelo):
    markdown = montar_markdown(partes, respostas)
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
        if j.get("status") == "erro" and erro_passageiro(RuntimeError(j.get("erro") or ""))
    ]


def _rodar_passada(fila, pendentes):
    falhas_seguidas = 0
    for numero, (pasta, job) in enumerate(pendentes):
        if numero > 0:
            time.sleep(PAUSA_ENTRE_LICITACOES)  # evita consultas em sequência rápida
        try:
            processar_job(fila, pasta, job)
            job["status"] = "concluido"
            job["erro"] = None
            falhas_seguidas = 0
        except Exception as erro:
            job["status"] = "erro"
            job["erro"] = str(erro)
            print(f"    ERRO: {erro}")
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
    motivo_parada: str | None = None   # "sem_modelo" | "sem_login" | None (rodou normalmente)
    detalhe: str = ""                  # mensagem do problema, quando houve parada
    concluidos: int = 0
    total: int = 0
    falhas: list = field(default_factory=list)  # [(nome da licitação, mensagem de erro)]


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
    )


def processar_fila():
    fila = carregar_fila()
    pendentes = [(p, j) for p, j in fila.items() if j.get("status") != "concluido"]

    print(f"\n===== FILA NOTEBOOKLM: {len(pendentes)} pendente(s) =====")
    if not pendentes:
        return _resultado(fila)

    if not os.path.exists(MODELO_RELATORIO):
        detalhe = f"Modelo de relatório não encontrado: {MODELO_RELATORIO}"
        print(detalhe)
        print("Coloque o arquivo modelo_relatorio.pdf nessa pasta (ou ajuste MODELO_RELATORIO em config.py).")
        return _resultado(fila, "sem_modelo", detalhe)

    try:
        testar_conexao()
    except Exception as erro:
        print(f"Não consegui falar com o NotebookLM: {erro}")
        return _resultado(fila, "sem_login", str(erro))

    for passada in range(1, MAX_PASSADAS + 1):
        if passada > 1:
            pendentes = [(p, fila[p]) for p in _falhas_passageiras(fila)]
            print(f"\n===== PASSADA {passada}/{MAX_PASSADAS}: {len(pendentes)} para tentar de novo =====")

        completou = _rodar_passada(fila, pendentes)
        restantes = _falhas_passageiras(fila)

        if not completou or not restantes or passada == MAX_PASSADAS:
            break

        print(f"\n{len(restantes)} sem resposta. Nova passada em {ESPERA_ENTRE_PASSADAS // 60} min...")
        time.sleep(ESPERA_ENTRE_PASSADAS)

    resultado = _resultado(fila)
    print(f"\nFila: {resultado.concluidos}/{resultado.total} concluído(s). Estado em: {ARQUIVO_FILA}")
    return resultado
