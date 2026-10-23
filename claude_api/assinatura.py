"""Claude pela ASSINATURA (Pro ou Max), usando o Claude Code instalado no computador.

Em vez de chamar a API (cobrada por uso), o programa roda "claude -p" (modo não
interativo do Claude Code), que gasta a cota da assinatura do usuário logado.

Como funciona cada licitação:
  - parte 1: os documentos (texto extraído aqui, com [Página N]) e o pedido vão pela
    entrada padrão do "claude -p". A resposta traz o ID da sessão;
  - parte 2: retoma a mesma sessão (--resume) mandando só o novo pedido, sem reenviar
    os documentos (economiza a cota).
  - PDF escaneado (sem texto): o Claude lê o arquivo com a ferramenta Read, que só é
    liberada nesse caso e só dentro da pasta da licitação.

Pré-requisitos (ver LEIA-ME.txt): Claude Code instalado e login feito com a conta da
assinatura ("claude auth login", ou a opção do menu).
"""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from claude_api.client import SISTEMA, ErroClaude, LimiteAssinatura, SemChave
from claude_api.documentos import TITULO_MODELO
from config import (
    CLAUDE_CODE_MODELO,
    CLAUDE_CODE_TIMEOUT,
    CLAUDE_ESFORCO,
    CLAUDE_ESPERA,
    CLAUDE_TENTATIVAS,
)

INSTALAR = "irm https://claude.ai/install.ps1 | iex"   # PowerShell (Windows)
LIMITE_ENTRADA = 9_500_000  # o "claude -p" aceita até 10 MB pela entrada padrão

SISTEMA_ASSINATURA = SISTEMA + """
Contexto de execução: você está sendo chamado por um programa, sem ninguém para conversar. \
Não crie nem altere arquivos e não execute comandos. Se houver PDFs escaneados indicados \
no pedido, leia-os com a ferramenta Read antes de responder. Sua resposta final deve ser \
somente o texto do relatório pedido.
"""

_arquivo_sistema = None


class SemClaudeCode(SemChave):
    """O Claude Code não está instalado (ou não foi encontrado)."""


def _executavel():
    exe = shutil.which("claude")
    if exe:
        return exe
    # O instalador nativo coloca o programa em ~/.local/bin, que às vezes não está no PATH
    for candidato in (Path.home() / ".local" / "bin" / "claude.exe",
                      Path.home() / ".local" / "bin" / "claude"):
        if candidato.is_file():
            return str(candidato)
    raise SemClaudeCode(
        "O Claude Code não está instalado neste computador. Para instalar, abra o "
        f"PowerShell e rode:  {INSTALAR}   (veja o LEIA-ME.txt)."
    )


def _ambiente():
    env = os.environ.copy()
    # Com uma chave de API no ambiente, o Claude Code cobraria pela API em vez de usar a assinatura
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return env


def login():
    """Abre o login da assinatura no navegador (interativo)."""
    return subprocess.run([_executavel(), "auth", "login"], env=_ambiente()).returncode == 0


def testar_conexao():
    """Confere se o Claude Code está instalado e logado (não gasta a cota)."""
    try:
        r = subprocess.run([_executavel(), "auth", "status"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60, env=_ambiente())
    except subprocess.TimeoutExpired:
        raise ErroClaude("Claude: o Claude Code não respondeu, temporariamente (timeout).",
                         passageiro=True)
    if r.returncode != 0:
        raise SemChave("Claude: o Claude Code não está logado na assinatura. Faça o login "
                       '(opção "Fazer login no Claude (assinatura)" do menu).')
    try:
        metodo = json.loads(r.stdout).get("authMethod")
    except (ValueError, AttributeError):
        metodo = None
    if metodo in ("api_key", "api_key_helper", "third_party"):
        print(f"    AVISO: o Claude Code está logado por '{metodo}', não pela assinatura: "
              "o uso pode ser cobrado à parte. Refaça o login pelo menu com a conta Pro/Max.")


def _caminho_sistema():
    global _arquivo_sistema
    if _arquivo_sistema is None or not os.path.exists(_arquivo_sistema):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt",
                                         prefix="algoritmo_claude_", delete=False) as f:
            f.write(SISTEMA_ASSINATURA)
            _arquivo_sistema = f.name
    return _arquivo_sistema


def _traduzir(mensagem, erro_repeticao=None):
    """Converte a falha do Claude Code em ErroClaude com mensagem em português."""
    baixo = (mensagem or "").lower()
    repeticao = (erro_repeticao or "").lower()

    if repeticao == "rate_limit" or ("limit" in baixo and any(
            t in baixo for t in ("reached", "hit your", "reset", "usage"))):
        return LimiteAssinatura(
            "Claude: o limite de uso da assinatura foi atingido (rate limit). Ele renova "
            "sozinho depois de algumas horas; enquanto isso, use o Gemini. "
            f"Detalhe: {mensagem[:150]}")
    if repeticao in ("authentication_failed", "oauth_org_not_allowed") or any(
            t in baixo for t in ("not logged", "login", "authentication", "invalid api key",
                                 "oauth", "unauthorized")):
        return SemChave("Claude: o login do Claude Code venceu ou não foi feito. Faça o login "
                        '(opção "Fazer login no Claude (assinatura)" do menu).')
    if repeticao in ("billing_error", "account_on_hold"):
        return ErroClaude(f"Claude: problema na conta/assinatura ({repeticao}): {mensagem[:200]}")
    if repeticao in ("overloaded", "server_error") or any(
            t in baixo for t in ("overloaded", "529", "internal server error", "503")):
        return ErroClaude("Claude: os servidores estão sobrecarregados, temporariamente.",
                          passageiro=True)
    return ErroClaude(f"Claude Code: {(mensagem or 'falhou sem mensagem').strip()[:300]}")


def _rodar(argumentos, entrada, pasta):
    """Roda "claude -p" com `entrada` pela entrada padrão. Devolve o evento final "result"."""
    comando = [_executavel(), "-p", "--output-format", "stream-json", "--verbose", *argumentos]
    proc = subprocess.Popen(comando, cwd=pasta, env=_ambiente(), stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace")

    def escrever():
        try:
            proc.stdin.write(entrada)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass  # o processo terminou antes (o erro aparece na saída)

    erros = []
    leitores = [threading.Thread(target=escrever, daemon=True),
                threading.Thread(target=lambda: erros.append(proc.stderr.read()), daemon=True)]
    for t in leitores:
        t.start()
    estourou = threading.Event()
    relogio = threading.Timer(CLAUDE_CODE_TIMEOUT, lambda: (estourou.set(), proc.kill()))
    relogio.start()

    resultado, erro_repeticao = None, None
    inicio = ultimo_aviso = time.time()
    try:
        for linha in proc.stdout:
            try:
                evento = json.loads(linha)
            except ValueError:
                continue
            tipo = evento.get("type")
            if tipo == "result":
                resultado = evento
            elif tipo == "system" and evento.get("subtype") == "api_retry":
                erro_repeticao = evento.get("error")
                if erro_repeticao == "rate_limit":  # cota esgotada: não adianta esperar aqui
                    proc.kill()
                    break
                print(f"      (o Claude Code está repetindo a consulta: {erro_repeticao})")
            agora = time.time()
            if agora - ultimo_aviso >= 30:
                ultimo_aviso = agora
                print(f"      ... analisando, {int(agora - inicio)}s")
        proc.wait()
    finally:
        relogio.cancel()
    for t in leitores:
        t.join(timeout=5)

    if estourou.is_set():
        raise ErroClaude(f"Claude: a análise passou de {CLAUDE_CODE_TIMEOUT // 60} minutos e foi "
                         "interrompida (timeout).", passageiro=True)
    if resultado is None:
        detalhe = ("".join(e for e in erros if e) or f"código de saída {proc.returncode}").strip()
        raise _traduzir(detalhe, erro_repeticao)
    if resultado.get("is_error") or resultado.get("subtype") != "success":
        raise _traduzir(str(resultado.get("result") or resultado.get("subtype") or ""),
                        erro_repeticao)

    segundos = time.time() - inicio
    print(f"      {int(segundos // 60)}min{int(segundos % 60):02d}s (assinatura, sem custo por uso)")
    return resultado


class Sessao:
    """Uma licitação = uma conversa do Claude Code (a parte 2 continua a parte 1)."""

    def __init__(self, pacote, pasta):
        self.pacote = pacote
        self.pasta = pasta
        self.sessao_id = None

    def _argumentos(self):
        args = ["--model", CLAUDE_CODE_MODELO,
                "--system-prompt-file", _caminho_sistema(),
                "--strict-mcp-config", "--disallowedTools", "mcp__*",
                "--permission-mode", "dontAsk"]
        if CLAUDE_ESFORCO:
            args += ["--effort", CLAUDE_ESFORCO]
        if self.pacote.pdfs:  # PDFs escaneados: libera só a leitura, só na pasta da licitação
            args += ["--tools", "Read", "--allowedTools", "Read",
                     "--max-turns", str(5 + 10 * len(self.pacote.pdfs))]
        else:
            args += ["--tools", "", "--max-turns", "3"]
        return args

    def _entrada_completa(self, prompt):
        partes = ["A seguir estão o modelo do relatório e os documentos da licitação.\n",
                  f'<modelo titulo="{TITULO_MODELO}">\n{self.pacote.texto_modelo}\n</modelo>\n']
        for bloco in self.pacote.blocos:
            fonte = bloco["source"]
            if fonte["type"] != "text":
                continue  # PDFs (modelo e escaneados) vão de outro jeito
            contexto = f"({bloco['context']})\n" if bloco.get("context") else ""
            partes.append(f'<documento titulo="{bloco["title"]}">\n{contexto}{fonte["data"]}\n</documento>\n')
        if self.pacote.pdfs:
            partes.append("PDFs escaneados (sem texto extraível) que também fazem parte da licitação. "
                          "Leia cada um com a ferramenta Read antes de responder:")
            for titulo, caminho in self.pacote.pdfs:
                partes.append(f"- {titulo}: {os.path.relpath(caminho, self.pasta)}")
            partes.append("")
        partes.append(f"PEDIDO:\n{prompt}")
        return "\n".join(partes)

    def _consulta_unica(self, prompt):
        if self.sessao_id:
            try:
                resultado = _rodar(self._argumentos() + ["--resume", self.sessao_id], prompt, self.pasta)
            except (LimiteAssinatura, SemChave):
                raise
            except ErroClaude as erro:
                print(f"      Não deu para continuar a conversa ({erro}); reenviando os documentos.")
                self.sessao_id = None
                return self._consulta_unica(prompt)
        else:
            entrada = self._entrada_completa(prompt)
            if len(entrada.encode("utf-8")) > LIMITE_ENTRADA:
                raise ErroClaude("Claude: os documentos desta licitação passam de 10 MB de texto, "
                                 "o máximo que o Claude Code aceita de uma vez.")
            resultado = _rodar(self._argumentos(), entrada, self.pasta)

        self.sessao_id = resultado.get("session_id") or self.sessao_id
        texto = str(resultado.get("result") or "").strip()
        if not texto:
            raise ErroClaude("Claude: a resposta veio vazia, temporariamente.", passageiro=True)
        return texto

    def consultar(self, prompt):
        """Consulta com repetição para falhas passageiras (o limite da assinatura não é repetido)."""
        for tentativa in range(1, CLAUDE_TENTATIVAS + 1):
            try:
                return self._consulta_unica(prompt)
            except (LimiteAssinatura, SemChave):
                raise
            except ErroClaude as erro:
                if not erro.passageiro or tentativa == CLAUDE_TENTATIVAS:
                    raise
                espera = CLAUDE_ESPERA * tentativa
                print(f"    {erro}")
                print(f"    Nova tentativa ({tentativa + 1}/{CLAUDE_TENTATIVAS}) em {espera}s...")
                time.sleep(espera)
