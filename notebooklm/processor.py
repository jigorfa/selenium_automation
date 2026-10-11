"""Processa a fila: cria o notebook, envia as fontes, roda o prompt, salva a resposta."""
import json
import os
import time

from config import (
    ARQUIVO_FILA,
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
    erro_passageiro,
    testar_conexao,
)
from notebooklm.prompts import obter_prompts
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
    arquivos_parte = []

    for n, (_, prompt) in enumerate(partes):
        arq = os.path.join(pasta, f"parte_{n + 1}{EXTENSAO_PARTE}")
        arquivos_parte.append(arq)

        if os.path.exists(arq):  # respondida numa tentativa anterior: não gasta consulta
            with open(arq, encoding="utf-8") as f:
                respostas[n] = f.read()
            print(f"    Parte {n + 1}/{len(partes)} já respondida; reaproveitando.")
            continue

        if n > 0:
            time.sleep(PAUSA_APOS_UPLOAD)
        print(f"    Executando o prompt, parte {n + 1}/{len(partes)} (pode demorar alguns minutos)...")
        try:
            respostas[n] = extrair_resposta(consultar(notebook_id, prompt))
        except Exception:
            if respostas:  # não perde o que já veio: grava o relatório parcial
                _salvar_relatorio(partes, respostas, destino, modelo)
            raise

        with open(arq, "w", encoding="utf-8") as f:
            f.write(respostas[n])

    _salvar_relatorio(partes, respostas, destino, modelo)
    for arq in arquivos_parte:  # relatório completo: o cache de retomada não é mais preciso
        if os.path.exists(arq):
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
               "Rode python main.py --fila para completar.]**"
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


def processar_fila():
    fila = carregar_fila()
    pendentes = [(p, j) for p, j in fila.items() if j.get("status") != "concluido"]

    print(f"\n===== FILA NOTEBOOKLM: {len(pendentes)} pendente(s) =====")
    if not pendentes:
        return

    if not os.path.exists(MODELO_RELATORIO):
        print(f"Modelo de relatório não encontrado: {MODELO_RELATORIO}")
        print("Ajuste MODELO_RELATORIO em config.py e rode: python main.py --fila")
        return

    try:
        testar_conexao()
    except Exception as erro:
        print(f"Não consegui falar com o NotebookLM: {erro}")
        print("Se for login, rode 'nlm login' e depois: python main.py --fila")
        return

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

    concluidos = sum(1 for j in fila.values() if j["status"] == "concluido")
    print(f"\nFila: {concluidos}/{len(fila)} concluído(s). Estado em: {ARQUIVO_FILA}")
    for pasta in _falhas_passageiras(fila):
        print(f"   sem resposta: {os.path.basename(pasta)}  (notebook {fila[pasta].get('notebook_id')})")
