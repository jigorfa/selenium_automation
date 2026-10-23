"""Fila persistente (JSON) das licitações a enviar ao NotebookLM."""
import glob
import json
import os

from config import ARQUIVO_FILA, EXTENSAO_PARTE


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
