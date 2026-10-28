"""Download direto dos anexos: pega o href do HTML e baixa com requests, sem clicar.

Pop-ups só atrapalham CLIQUES. Lendo o href do link e baixando por fora do navegador,
um pop-up na frente do link deixa de importar. A sessão do Selenium (cookies, user-agent)
é reaproveitada para continuar autenticado.

O arquivo é gravado na pasta de downloads (config.DOWNLOAD_DIR), do mesmo jeito que o
Firefox faria, e o resto do programa (aguardar_downloads / mover_arquivos_novos) segue igual.
"""
import mimetypes
import os
import re
import time
from email.message import Message
from urllib.parse import unquote, urlparse

import requests

from browser.downloads import nome_seguro
from config import DOWNLOAD_DIR

TIMEOUT_CONEXAO = 15       # segundos para conectar
TIMEOUT_LEITURA = 120      # segundos sem receber dados
TENTATIVAS = 3
ESPERA_ENTRE_TENTATIVAS = 2


class DownloadDiretoFalhou(Exception):
    """O link não pôde ser baixado direto (o chamador pode tentar clicando nele)."""


def url_baixavel(href):
    """True se o href é um endereço http(s) que o requests consegue baixar."""
    return bool(href) and urlparse(href).scheme in ("http", "https")


def criar_sessao(driver):
    """Sessão requests com os cookies e o user-agent do navegador (login já feito)."""
    sessao = requests.Session()
    for cookie in driver.get_cookies():
        sessao.cookies.set(
            cookie["name"], cookie["value"],
            domain=cookie.get("domain") or None, path=cookie.get("path") or "/",
        )
    try:
        sessao.headers["User-Agent"] = driver.execute_script("return navigator.userAgent")
    except Exception:
        pass
    try:
        sessao.headers["Referer"] = driver.current_url
    except Exception:
        pass
    return sessao


def _corrigir_acentos(nome):
    """Servidores mandam o nome em UTF-8 e o requests lê o cabeçalho como latin-1."""
    try:
        return nome.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return nome


def nome_do_arquivo(resposta, url, indice=1):
    """Nome do arquivo: Content-Disposition, senão o final da URL, senão 'anexo_N'."""
    nome = None

    disposicao = resposta.headers.get("Content-Disposition")
    if disposicao:
        msg = Message()
        msg["Content-Disposition"] = disposicao
        nome = msg.get_filename()
        if nome and "filename*" not in disposicao.lower():
            nome = _corrigir_acentos(nome)

    if not nome:
        nome = unquote(os.path.basename(urlparse(url).path))

    nome = nome or f"anexo_{indice}"

    raiz, extensao = os.path.splitext(nome)
    if not extensao:  # sem extensão: tenta descobrir pelo tipo do arquivo
        tipo = (resposta.headers.get("Content-Type") or "").split(";")[0].strip()
        extensao = mimetypes.guess_extension(tipo) or ""
    extensao = re.sub(r"[^A-Za-z0-9.]", "", extensao)[:10]
    return nome_seguro(raiz) + extensao


def _caminho_livre(nome):
    """Caminho em DOWNLOAD_DIR que ainda não existe ('a.pdf' -> 'a (1).pdf'), como o Firefox faz.
    Assim um arquivo antigo com o mesmo nome nunca é sobrescrito sem ninguém notar."""
    raiz, extensao = os.path.splitext(nome)
    caminho = os.path.join(DOWNLOAD_DIR, nome)
    numero = 1
    while os.path.exists(caminho) or os.path.exists(caminho + ".part"):
        caminho = os.path.join(DOWNLOAD_DIR, f"{raiz} ({numero}){extensao}")
        numero += 1
    return caminho


def baixar_url(sessao, url, indice=1):
    """Baixa `url` para DOWNLOAD_DIR e devolve o caminho do arquivo.

    Levanta DownloadDiretoFalhou se não for possível (sem permissão, página HTML em vez
    de arquivo, erro de rede depois das tentativas...)."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    ultimo_erro = "sem resposta"

    for tentativa in range(1, TENTATIVAS + 1):
        parcial = None
        try:
            with sessao.get(url, stream=True, allow_redirects=True,
                            timeout=(TIMEOUT_CONEXAO, TIMEOUT_LEITURA)) as resposta:
                if resposta.status_code in (401, 403, 404):
                    # Repetir não adianta: provável falta de login/permissão
                    raise DownloadDiretoFalhou(f"HTTP {resposta.status_code}")
                if resposta.status_code >= 400:
                    raise requests.HTTPError(f"HTTP {resposta.status_code}")

                tipo = (resposta.headers.get("Content-Type") or "").lower()
                anexo = "attachment" in (resposta.headers.get("Content-Disposition") or "").lower()
                if tipo.startswith("text/html") and not anexo:
                    # Redirecionou para tela de login/erro: não é o documento
                    raise DownloadDiretoFalhou("o link devolveu uma página HTML, não um arquivo")

                caminho = _caminho_livre(nome_do_arquivo(resposta, resposta.url, indice))
                parcial = caminho + ".part"  # mesmo sufixo do Firefox: aguardar_downloads espera
                with open(parcial, "wb") as arquivo:
                    for pedaco in resposta.iter_content(chunk_size=64 * 1024):
                        arquivo.write(pedaco)

            esperado = resposta.headers.get("Content-Length")
            if (esperado and not resposta.headers.get("Content-Encoding")
                    and os.path.getsize(parcial) != int(esperado)):
                raise requests.ConnectionError("download incompleto")

            os.replace(parcial, caminho)
            return caminho

        except DownloadDiretoFalhou:
            _apagar(parcial)
            raise
        except (requests.RequestException, OSError) as erro:
            _apagar(parcial)
            ultimo_erro = f"{type(erro).__name__}: {str(erro)[:120]}"
            if tentativa < TENTATIVAS:
                time.sleep(ESPERA_ENTRE_TENTATIVAS * tentativa)

    raise DownloadDiretoFalhou(ultimo_erro)


def _apagar(caminho):
    if caminho:
        try:
            os.remove(caminho)
        except OSError:
            pass
