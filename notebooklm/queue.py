"""Fila persistente (JSON) das licitações a enviar ao NotebookLM."""
import glob
import json
import os

from config import ARQUIVO_FILA, EXTENSAO_PARTE, NOME_RELATORIO, NOME_RESPOSTA


def carregar_fila():
    """Lê a fila. Arquivo ausente ou vazio = fila vazia; arquivo corrompido vira backup."""
    if not os.path.exists(ARQUIVO_FILA):
        return {}

    # utf-8-sig também aceita arquivos salvos com BOM (comum no Bloco de Notas)
    with open(ARQUIVO_FILA, encoding="utf-8-sig") as f:
        conteudo = f.read()

    if not conteudo.strip():
        return {}

    try:
        fila = json.loads(conteudo)
        if isinstance(fila, dict):
            return fila
        raise ValueError("a fila deve ser um objeto JSON ({...})")
    except ValueError as erro:  # JSONDecodeError é um ValueError
        backup = ARQUIVO_FILA + ".corrompido"
        os.replace(ARQUIVO_FILA, backup)
        print(f"    AVISO: {os.path.basename(ARQUIVO_FILA)} inválido ({erro}). "
              f"Guardei uma cópia em {os.path.basename(backup)} e comecei uma fila nova.")
        return {}


def salvar_fila(fila):
    temporario = ARQUIVO_FILA + ".tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(fila, f, ensure_ascii=False, indent=2)
    os.replace(temporario, ARQUIVO_FILA)


def _tem_relatorio(pasta):
    """True se a pasta tem o relatório esperado (relatorio.docx com conteúdo).

    Se o .docx não pôde ser montado, o programa guarda a resposta bruta em
    resposta_notebooklm.txt; isso também conta, senão cada execução gastaria consultas
    da IA de novo só para falhar outra vez na montagem do .docx."""
    for nome in (NOME_RELATORIO, NOME_RESPOSTA):
        caminho = os.path.join(pasta, nome)
        try:
            if os.path.getsize(caminho) > 0:
                return True
        except OSError:
            continue
    return False


def reenfileirar_sem_relatorio(somente=None):
    """Volta para a fila as licitações marcadas como concluídas cujo relatório sumiu da pasta.

    O status "concluido" fica gravado na fila, então apagar o relatório não bastava para
    refazê-lo. Aqui a pasta é conferida: se o relatório não está lá, a licitação fica
    "pendente" de novo (os arquivos baixados e o notebook já enviado são reaproveitados).
    Pastas que não existem mais são ignoradas (não há o que processar).
    `somente` (conjunto de pastas) limita a conferência a essas licitações.
    Devolve a lista das pastas que voltaram para a fila."""
    fila = carregar_fila()
    voltaram = []

    for pasta, job in fila.items():
        if job.get("status") != "concluido":
            continue
        if somente is not None and pasta not in somente:
            continue
        if not os.path.isdir(pasta) or _tem_relatorio(pasta):
            continue
        job["status"] = "pendente"
        job["erro"] = None
        voltaram.append(pasta)

    if voltaram:
        salvar_fila(fila)
        print(f"\n{len(voltaram)} licitação(ões) sem o relatório na pasta; voltaram para a fila:")
        for pasta in voltaram:
            print(f"  - {os.path.basename(pasta)}")

    return voltaram


def enfileirar(licitacao, novo_ciclo=True):
    """Recebe um models.Licitacao e guarda tudo que o --fila vai precisar.

    Se a pasta já estava na fila (data refeita), ela volta a ficar pendente:
    reaproveita o notebook e os arquivos já enviados e só refaz a consulta.

    novo_ciclo=True (download novo) zera as marcas de "sem arquivos"/"baixado de novo";
    False é usado quando a própria nova tentativa de download recoloca a licitação na fila."""
    fila = carregar_fila()
    pasta = os.path.abspath(licitacao.pasta)

    dados = {
        "titulo": licitacao.titulo,
        "fonte": licitacao.fonte,
        "perfil": licitacao.perfil,
        "data": licitacao.data,
        "prompt": licitacao.prompt,
    }

    if pasta not in fila:
        fila[pasta] = {
            **dados,
            "status": "pendente",
            "notebook_id": None,
            "arquivos_enviados": [],
            "erro": None,
        }
        print(f"    Adicionada à fila de relatórios: {os.path.basename(pasta)}")
    else:
        fila[pasta].update(dados)
        # Refazer a data = respostas novas: descarta respostas parciais antigas
        for antigo in glob.glob(os.path.join(glob.escape(pasta), f"*{EXTENSAO_PARTE}")):
            os.remove(antigo)
        fila[pasta]["status"] = "pendente"
        fila[pasta]["erro"] = None
        if novo_ciclo:
            fila[pasta].pop("sem_arquivos", None)
            fila[pasta].pop("redownload_tentado", None)
        print(f"    Já estava na fila; será processada de novo: {os.path.basename(pasta)}")

    salvar_fila(fila)
