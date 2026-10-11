"""Acesso ao NotebookLM via CLI "nlm" (biblioteca não oficial)."""
import re
import shutil
import subprocess
import time

from config import CONSULTA_ESPERA, CONSULTA_TENTATIVAS

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")


def run_nlm(args, timeout=300):
    exe = shutil.which("nlm")
    if not exe:
        raise RuntimeError(
            "Comando 'nlm' não encontrado. Instale com: "
            "uv tool install notebooklm-mcp-cli  (ou pip install notebooklm-mcp-cli) "
            "e depois rode: nlm login"
        )

    resultado = subprocess.run(
        [exe] + args,
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


def consultar(notebook_id, prompt):
    for tentativa in range(1, CONSULTA_TENTATIVAS + 1):
        try:
            return run_nlm(
                ["notebook", "query", notebook_id, prompt, "--json", "--timeout", "300"],
                timeout=400,
            )
        except (RuntimeError, subprocess.TimeoutExpired) as erro:
            if tentativa == CONSULTA_TENTATIVAS or not erro_passageiro(erro):
                raise
            espera = CONSULTA_ESPERA * tentativa
            print(f"    Sem resposta (tentativa {tentativa}/{CONSULTA_TENTATIVAS}); "
                  f"nova tentativa em {espera}s...")
            time.sleep(espera)
