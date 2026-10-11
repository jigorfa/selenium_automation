"""Extração de zips e seleção dos arquivos que viram fontes do notebook."""
import os
import shutil
import zipfile

from config import ARQUIVOS_GERADOS, EXTENSOES_FONTE


def _nome_zip_correto(info):
    """Corrige acentos em zips criados no Windows (nomes em cp850)."""
    nome = info.filename
    if not (info.flag_bits & 0x800):
        try:
            bruto = nome.encode("cp437")
            try:
                nome = bruto.decode("utf-8")
            except UnicodeDecodeError:
                nome = bruto.decode("cp850")
        except UnicodeEncodeError:
            pass
    return nome


def extrair_zips(pasta):
    """Extrai todos os .zip (inclusive aninhados) para pasta/extraidos/<nome_do_zip>/."""
    base = os.path.join(pasta, "extraidos")
    processados = set()

    while True:
        zips = [
            os.path.join(raiz, arq)
            for raiz, _, arquivos in os.walk(pasta)
            for arq in arquivos
            if arq.lower().endswith(".zip")
            and os.path.join(raiz, arq) not in processados
        ]
        if not zips:
            break

        for caminho in zips:
            processados.add(caminho)
            nome_zip = os.path.splitext(os.path.basename(caminho))[0]
            destino = os.path.abspath(os.path.join(base, nome_zip))
            print(f"    Extraindo: {os.path.basename(caminho)}")

            try:
                with zipfile.ZipFile(caminho) as z:
                    for info in z.infolist():
                        if info.is_dir():
                            continue
                        nome = _nome_zip_correto(info).replace("\\", "/")
                        alvo = os.path.abspath(os.path.join(destino, *nome.split("/")))
                        if not alvo.startswith(destino + os.sep):
                            continue  # evita caminhos fora da pasta
                        os.makedirs(os.path.dirname(alvo), exist_ok=True)
                        with z.open(info) as origem, open(alvo, "wb") as saida:
                            shutil.copyfileobj(origem, saida)
            except zipfile.BadZipFile:
                print(f"    Zip inválido/corrompido: {caminho}")

    for raiz, _, arquivos in os.walk(pasta):
        for arq in arquivos:
            if arq.lower().endswith((".rar", ".7z")):
                print(f"    Aviso: {arq} não é suportado (só .zip); extraia manualmente.")


def coletar_arquivos(pasta):
    encontrados = []
    for raiz, _, arquivos in os.walk(pasta):
        for arq in arquivos:
            if arq in ARQUIVOS_GERADOS:
                continue
            if os.path.splitext(arq)[1].lower() in EXTENSOES_FONTE:
                encontrados.append(os.path.join(raiz, arq))
    return sorted(encontrados)


def descrever_pasta(pasta):
    """Explica o que há na pasta quando nenhum arquivo serve (para diagnosticar o erro)."""
    if not os.path.isdir(pasta):
        return f"A pasta não existe: {pasta} (foi movida/apagada? caminho de outra máquina?)"

    nomes = [
        os.path.relpath(os.path.join(raiz, arq), pasta)
        for raiz, _, arquivos in os.walk(pasta)
        for arq in arquivos
        if arq not in ARQUIVOS_GERADOS
    ]
    if not nomes:
        return f"A pasta está vazia: {pasta}"

    exemplos = ", ".join(sorted(nomes)[:5])
    extra = f" (+{len(nomes) - 5})" if len(nomes) > 5 else ""
    return (f"Arquivos encontrados, mas de tipo não aceito: {exemplos}{extra}. "
            f"Tipos aceitos: {', '.join(sorted(EXTENSOES_FONTE))}")
