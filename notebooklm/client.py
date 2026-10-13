"""Acesso ao NotebookLM via CLI "nlm" (biblioteca não oficial)."""
import os
import re
import shutil
import subprocess
import sys
import time

import config
from config import CONSULTA_ESPERA, CONSULTA_TENTATIVAS

# True = cada consulta abre uma conversa nova no notebook (não arrasta respostas
# falhas anteriores). Se a versão do "nlm" não conhecer a opção, é desligado sozinho.
_NOVA_CONVERSA = getattr(config, "NOVA_CONVERSA_POR_CONSULTA", True)


class SemResposta(RuntimeError):
    """O NotebookLM devolveu resposta vazia ("Não foi possível gerar uma resposta").

    Repetir o MESMO prompt costuma falhar de novo (e gasta o limite diário), por isso
    isto é separado dos erros passageiros: quem chama decide (ex.: dividir o prompt)."""

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")


def _comando_nlm():
    """No .exe, o "nlm" vem embutido: o próprio programa se chama com --nlm (ver main.py)."""
    if config.EXECUTAVEL:
        return [sys.executable, "--nlm"]

    exe = shutil.which("nlm")
    if not exe:
        raise RuntimeError(
            "Comando 'nlm' não encontrado. Instale com: "
            "uv tool install notebooklm-mcp-cli  (ou pip install notebooklm-mcp-cli) "
            "e depois rode: nlm login"
        )
    return [exe]


def _ambiente_nlm():
    env = os.environ.copy()
    base_url = getattr(config, "NOTEBOOKLM_BASE_URL", "")
    if base_url:
        env.setdefault("NOTEBOOKLM_BASE_URL", base_url)
    return env


def login_nlm(forcar=False):
    """Abre o login do NotebookLM (interativo: o navegador abre e o usuário entra na conta)."""
    args = _comando_nlm() + ["login"] + (["--force"] if forcar else [])
    return subprocess.run(args, env=_ambiente_nlm()).returncode == 0


def run_nlm(args, timeout=300):
    resultado = subprocess.run(
        _comando_nlm() + args,
        env=_ambiente_nlm(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )

    if resultado.returncode != 0:
        detalhe = (resultado.stderr or resultado.stdout).strip()[:500]
        raise RuntimeError(f"nlm {' '.join(args[:2])} falhou: {detalhe}")

    return resultado.stdout


def testar_conexao():
    run_nlm(["notebook", "list"], timeout=60)


def criar_notebook(titulo):
    saida = run_nlm(["notebook", "create", titulo], timeout=120)
    achado = UUID_RE.search(saida)
    if not achado:
        raise RuntimeError(f"Não achei o ID do notebook na saída: {saida.strip()[:300]}")
    return achado.group(0)


def adicionar_arquivo(notebook_id, arquivo):
    run_nlm(["source", "add", notebook_id, "--file", arquivo, "--wait"], timeout=600)


# Trechos de mensagem que indicam falha passageira (vale tentar de novo)
ERROS_PASSAGEIROS = (
    "no answer", "retry", "rate limit", "429", "quota",
    "timed out", "timeout", "temporar", "unavailable", "503",
)
# ...exceto se o problema for de login: repetir não adianta
ERROS_DE_LOGIN = ("login", "auth", "cookie", "sign in")


def erro_passageiro(erro):
    """True se a falha é passageira (sem resposta, limite, timeout) e vale tentar de novo."""
    if isinstance(erro, subprocess.TimeoutExpired):
        return True
    msg = str(erro).lower()
    if any(t in msg for t in ERROS_DE_LOGIN):
        return False
    return any(t in msg for t in ERROS_PASSAGEIROS)


def _sem_resposta(erro):
    return "no answer" in str(erro).lower()


def _consulta_unica(notebook_id, prompt):
    global _NOVA_CONVERSA
    args = ["notebook", "query", notebook_id, prompt, "--json", "--timeout", "300"]
    if _NOVA_CONVERSA:
        try:
            return run_nlm(args + ["--new-conversation"], timeout=400)
        except RuntimeError as erro:
            if "no such option" not in str(erro).lower():
                raise
            _NOVA_CONVERSA = False  # versão antiga do nlm: segue sem a opção
            print("    (nlm sem --new-conversation; usando a conversa padrão do notebook)")
    return run_nlm(args, timeout=400)


def consultar(notebook_id, prompt):
    """Faz a consulta. Falhas passageiras (timeout, limite) são repetidas com espera;
    "sem resposta" levanta SemResposta na hora, sem repetir o mesmo prompt."""
    for tentativa in range(1, CONSULTA_TENTATIVAS + 1):
        try:
            return _consulta_unica(notebook_id, prompt)
        except (RuntimeError, subprocess.TimeoutExpired) as erro:
            if _sem_resposta(erro):
                raise SemResposta(str(erro)) from erro
            if tentativa == CONSULTA_TENTATIVAS or not erro_passageiro(erro):
                raise
            espera = CONSULTA_ESPERA * tentativa
            print(f"    Falha passageira (tentativa {tentativa}/{CONSULTA_TENTATIVAS}); "
                  f"nova tentativa em {espera}s...")
            time.sleep(espera)
