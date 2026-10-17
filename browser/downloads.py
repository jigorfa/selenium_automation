"""Pasta de downloads: espera terminar, move para a pasta da licitação."""
import os
import re
import shutil
import time

from config import DOWNLOAD_DIR


def listar_arquivos():
    """Foto do conteúdo atual da pasta de downloads (para comparar depois)."""
    return set(os.listdir(DOWNLOAD_DIR))


def aguardar_downloads(arquivos_antes, timeout=90, estabilidade=3):
    """Espera os downloads terminarem, olhando apenas os arquivos que
    realmente apareceram na pasta (sem depender de quantos links foram clicados).
    Termina quando há arquivos novos, nenhum .part e o tamanho parou de mudar."""
    limite = time.time() + timeout
    ultimo_estado = None
    desde = None

    while time.time() < limite:
        estado = []
        em_andamento = False

        for nome in set(os.listdir(DOWNLOAD_DIR)) - arquivos_antes:
            caminho = os.path.join(DOWNLOAD_DIR, nome)
            try:
                if not os.path.isfile(caminho):
                    continue
                tamanho = os.path.getsize(caminho)
            except OSError:
                continue  # arquivo renomeado (.part -> final) neste instante

            if nome.endswith(".part"):
                em_andamento = True
            estado.append((nome, tamanho))

        estado = tuple(sorted(estado))
        concluidos = [n for n, _ in estado if not n.endswith(".part")]

        if concluidos and not em_andamento:
            if estado != ultimo_estado:
                ultimo_estado = estado
                desde = time.time()
            elif time.time() - desde >= estabilidade:
                return sorted(concluidos)
        else:
            ultimo_estado = None

        time.sleep(0.5)

    return None


def mover_arquivos_novos(arquivos_antes, pasta):
    movidos = []
    for nome in sorted(set(os.listdir(DOWNLOAD_DIR)) - arquivos_antes):
        origem = os.path.join(DOWNLOAD_DIR, nome)
        if nome.endswith(".part") or not os.path.isfile(origem):
            continue
        if os.path.getsize(origem) == 0:
            print(f"    ATENÇÃO: o download de {nome} veio VAZIO (0 bytes); ele precisará ser baixado de novo.")
        destino = os.path.join(pasta, nome)
        if os.path.exists(destino):  # download repetido: o novo substitui o antigo (no Windows o move falharia)
            os.remove(destino)
        shutil.move(origem, destino)
        movidos.append(nome)
    return movidos


def remover_arquivos_vazios(pasta):
    """Apaga os arquivos de 0 bytes da pasta (downloads que falharam) antes de baixar de novo."""
    for raiz, _, arquivos in os.walk(pasta):
        for arq in arquivos:
            caminho = os.path.join(raiz, arq)
            if os.path.getsize(caminho) == 0:
                os.remove(caminho)
                print(f"    Removido arquivo vazio: {arq}")


def nome_seguro(texto, limite=80):
    texto = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", texto)
    texto = re.sub(r"\s+", " ", texto).strip(" .")
    return texto[:limite].strip(" .") or "sem_titulo"


def pasta_da_licitacao(fonte, data, empresa, numero, titulo):
    """downloads/<fonte>/<DD-MM-AAAA>/<empresa>/<NN>_<titulo>/"""
    dia = data.replace("/", "-")
    pasta = os.path.join(
        DOWNLOAD_DIR, fonte, dia, nome_seguro(empresa or "sem_empresa"),
        f"{numero:02d}_{nome_seguro(titulo)}",
    )
    os.makedirs(pasta, exist_ok=True)
    return pasta
