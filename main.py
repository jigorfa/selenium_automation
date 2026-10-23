"""Ponto de entrada: escolhe a fonte, coleta as licitações e gera os relatórios
com a ferramenta escolhida (Gemini/NotebookLM ou Claude).

Uso:
    python main.py                 # menu (ou duplo clique no .exe)
    python main.py --fila          # só processa a fila (pergunta a ferramenta)
    python main.py --fila --claude # só processa a fila, com o Claude (ou --gemini)
    python main.py --login         # só faz o login no NotebookLM
    python main.py --login-claude  # só faz o login no Claude (assinatura)
"""
import sys

# Modo interno do .exe: o programa se chama de novo para executar o "nlm" embutido.
# Precisa ficar ANTES dos outros imports (é rápido e não depende de Selenium etc.).
if len(sys.argv) > 1 and sys.argv[1] == "--nlm":
    from notebooklm_tools.cli.main import cli_main

    sys.argv = ["nlm"] + sys.argv[2:]
    cli_main()
    raise SystemExit(0)

import os
import re
import traceback
from datetime import datetime

from cli import confirmar, pedir_opcao
from claude_api import assinatura
from config import BASE_DIR, CLAUDE_MODO, COMO_REPROCESSAR, ENVIAR_NOTEBOOKLM, EXECUTAVEL, FERRAMENTAS
from fonts import FONTES
from notebooklm.client import ERROS_DE_LOGIN, erro_passageiro, login_nlm
from notebooklm.processor import processar_fila
from notebooklm.queue import carregar_fila, enfileirar, salvar_fila

OPCAO_COMPLETO = "Baixar licitações e gerar relatórios (fluxo completo)"
OPCAO_FILA = "Processar a fila de relatórios pendentes (sem baixar nada)"
OPCAO_LOGIN = "Fazer login no NotebookLM"
OPCAO_LOGIN_CLAUDE = "Fazer login no Claude (assinatura)"


def escolher_fonte():
    nomes = list(FONTES)
    if len(nomes) == 1:  # só uma fonte cadastrada: não precisa perguntar
        return FONTES[nomes[0]]()

    nome = pedir_opcao("Fonte de licitações", nomes, confirmar_escolha=False)
    return FONTES[nome]()


def escolher_ferramenta(titulo="Ferramenta para gerar as análises"):
    """Pergunta Gemini ou Claude e devolve a chave ("gemini"/"claude")."""
    for chave in FERRAMENTAS:  # --claude / --gemini na linha de comando: não pergunta
        if f"--{chave}" in sys.argv:
            sys.argv.remove(f"--{chave}")  # vale só na primeira pergunta
            print(f"\nFerramenta: {FERRAMENTAS[chave]}")
            return chave

    por_nome = {nome: chave for chave, nome in FERRAMENTAS.items()}
    return por_nome[pedir_opcao(titulo, list(por_nome), confirmar_escolha=False)]


def explicar_chave_claude():
    if CLAUDE_MODO == "assinatura":
        print("\nPara usar o Claude pela assinatura (uma vez só em cada computador):")
        print("  1. Tenha uma assinatura Claude Pro ou Max (claude.ai).")
        print("  2. Instale o Claude Code: abra o PowerShell e rode")
        print(f"       {assinatura.INSTALAR}")
        print('  3. Abra este programa e escolha "Fazer login no Claude (assinatura)".')
        print("  Veja o LEIA-ME.txt para o passo a passo.")
        return
    print("\nPara usar o Claude é preciso uma chave da API (uma vez só):")
    print("  1. Entre em https://platform.claude.com, crie a chave em Settings > API keys")
    print("     (https://platform.claude.com/settings/keys) e adicione créditos em Billing.")
    print("  2. No accounts.py (na pasta do programa), acrescente a linha:")
    print('       CLAUDE = {"api_key": "sk-ant-...sua chave..."}')
    print("  Veja o LEIA-ME.txt para o passo a passo.")


# ---------------------------------------------------------------------------
# Fila do NotebookLM com orientação ao usuário
# ---------------------------------------------------------------------------
def _resumir_erro(texto, limite=150):
    """Deixa a mensagem de erro em uma linha curta e legível."""
    texto = re.sub(r"\s+", " ", texto or "").strip()
    return texto if len(texto) <= limite else texto[:limite - 3] + "..."


def _e_erro_de_login(texto):
    return any(trecho in (texto or "").lower() for trecho in ERROS_DE_LOGIN)


def fazer_login():
    print("\nVai abrir o navegador. Entre na conta Google que usa o NotebookLM e aguarde a janela fechar.\n")
    if login_nlm(forcar=True):
        print("\nLogin concluído.")
        return True
    print("\nO login não foi concluído. Tente de novo (a janela do navegador precisa fechar sozinha).")
    return False


def _dicas_gemini(falhas):
    if any(_e_erro_de_login(e) for _, e in falhas):
        print("  * Parece problema de LOGIN no NotebookLM: refaça o login e tente de novo.")
    if all(erro_passageiro(RuntimeError(e)) for _, e in falhas):
        print("  * O NotebookLM não respondeu. Costuma ser instabilidade ou o limite diário de consultas.")
        print("    Tentar de novo agora às vezes funciona; se falhar outra vez, espere de 30 a 60 minutos")
        print("    ou tente amanhã. O que já foi respondido fica salvo e não é refeito.")
        print("  * Ou tente de novo escolhendo o Claude, que não tem esse limite diário.")


def fazer_login_claude():
    print("\nVai abrir o navegador. Entre com a conta da assinatura Claude (Pro ou Max).\n")
    try:
        ok = assinatura.login()
    except Exception as erro:  # ex.: Claude Code não instalado
        print(f"\n{erro}")
        return False
    print("\nLogin concluído." if ok else "\nO login não foi concluído. Tente de novo.")
    return ok


def _dicas_claude(falhas):
    if any("Chave da API do Claude" in e or "chave da API" in e for _, e in falhas):
        print("  * Problema com a CHAVE da API do Claude:")
        explicar_chave_claude()
    if any("login do Claude Code" in e or "não está instalado" in e for _, e in falhas):
        print("  * Problema com o Claude Code (instalação ou login):")
        explicar_chave_claude()
    if any("limite de uso da assinatura" in e for _, e in falhas):
        print("  * O limite de uso da assinatura do Claude acabou. Ele renova sozinho depois de")
        print("    algumas horas. Enquanto isso, gere os que faltam com o Gemini.")
    if any("sem créditos" in e for _, e in falhas):
        print("  * A conta da API do Claude está sem créditos: adicione em platform.claude.com > Billing.")
    if all(erro_passageiro(RuntimeError(e)) for _, e in falhas):
        print("  * A API do Claude estava sobrecarregada, no limite ou sem conexão. Costuma passar em")
        print("    poucos minutos: tente de novo. O que já foi respondido fica salvo e não é refeito.")


def mostrar_falhas(resultado, ferramenta="gemini"):
    """Lista os relatórios que NÃO foram gerados e diz o que fazer."""
    falhas = resultado.falhas
    print("\n" + "=" * 60)
    print(f"ATENÇÃO: {len(falhas)} relatório(s) NÃO foram gerados "
          f"({resultado.concluidos} de {resultado.total} concluídos):")
    for nome, erro in falhas:
        print(f"  - {nome}")
        print(f"      motivo: {_resumir_erro(erro)}")

    print("\nO que fazer:")
    if ferramenta == "claude":
        _dicas_claude(falhas)
    else:
        _dicas_gemini(falhas)
    if any("Nenhum arquivo compatível" in e or "conteúdo legível" in e for _, e in falhas):
        print("  * Licitação sem arquivo utilizável, mesmo depois de baixar de novo: baixe os anexos")
        print("    manualmente pelo Effecti, coloque-os na pasta da licitação e processe a fila.")
    print(f"  * Para tentar mais tarde, {COMO_REPROCESSAR}.")
    print("=" * 60)


def rebaixar_remanescentes(fonte, parametros, pastas):
    """Volta ao download das licitações que ficaram sem arquivo utilizável.

    Cada licitação ganha UMA nova tentativa de download (a marca fica gravada na fila);
    se continuar sem arquivo, ela é apenas listada como falha. Devolve o conjunto de pastas
    que foram baixadas de novo e recolocadas na fila."""
    print("\n" + "=" * 60)
    print(f"VOLTANDO AO DOWNLOAD: {len(pastas)} licitação(ões) ficaram sem arquivo utilizável:")
    for pasta in pastas:
        print(f"  - {os.path.basename(pasta)}")
    print("=" * 60)

    # Marca ANTES de baixar: haja o que houver, só se tenta uma vez por licitação
    fila = carregar_fila()
    for pasta in pastas:
        fila[pasta]["redownload_tentado"] = True
    salvar_fila(fila)

    try:
        novas = fonte.rebaixar(parametros, pastas)
    except Exception as erro:
        print(f"\nNão consegui baixar de novo: {type(erro).__name__}: {erro}")
        return set()

    reenfileiradas = set()
    for licitacao in novas:
        enfileirar(licitacao, novo_ciclo=False)  # mantém a marca "já baixada de novo"
        reenfileiradas.add(os.path.abspath(licitacao.pasta))

    sem_arquivo = [os.path.basename(p) for p in pastas if os.path.abspath(p) not in reenfileiradas]
    if sem_arquivo:
        print(f"\nO download não trouxe arquivos para {len(sem_arquivo)} licitação(ões); seguindo sem elas:")
        for nome in sem_arquivo:
            print(f"  - {nome}")
    return reenfileiradas


def _ha_pendentes():
    return any(j.get("status") != "concluido" for j in carregar_fila().values())


def processar_fila_interativo(fonte=None, parametros=None, ferramenta=None):
    """Processa a fila; se algo falhar, explica e pergunta se quer tentar de novo agora
    (podendo trocar de ferramenta: Gemini <-> Claude).

    Com `fonte` e `parametros` (fluxo completo), as licitações que ficaram sem arquivo
    utilizável voltam ao download uma vez, ao fim da fila, e são processadas de novo.
    Sem `ferramenta`, pergunta ao usuário qual usar."""
    if ferramenta is None:
        if not _ha_pendentes():
            print("\nNenhum relatório pendente na fila.")
            return
        ferramenta = escolher_ferramenta()

    while True:
        resultado = processar_fila(ferramenta=ferramenta)

        if resultado.motivo_parada == "sem_modelo":
            return

        if resultado.motivo_parada == "sem_login":
            print("\nNão foi possível acessar o NotebookLM (provavelmente o login venceu ou não foi feito).")
            if confirmar("Deseja fazer o login no NotebookLM agora?"):
                fazer_login()
                continue
            if confirmar("Deseja gerar os relatórios com o Claude no lugar?"):
                ferramenta = "claude"
                continue
            print(f"\nQuando fizer o login, {COMO_REPROCESSAR}.")
            return

        if resultado.motivo_parada == "limite":
            print("\nO limite de uso da assinatura do Claude acabou (ele renova sozinho depois de")
            print("algumas horas). O que já foi gerado está salvo.")
            if confirmar("\nDeseja gerar os que faltam com o Gemini (NotebookLM)?"):
                ferramenta = "gemini"
                continue
            print(f"\nQuando o limite renovar, {COMO_REPROCESSAR}.")
            return

        if resultado.motivo_parada in ("sem_chave", "sem_conexao"):
            if resultado.motivo_parada == "sem_chave":
                if CLAUDE_MODO == "assinatura" and "login" in resultado.detalhe and \
                        confirmar("\nDeseja fazer o login no Claude agora?"):
                    fazer_login_claude()
                    continue
                explicar_chave_claude()
            else:
                print("\nNão foi possível usar o Claude agora (o motivo está logo acima).")
            if confirmar("\nDeseja gerar os relatórios com o Gemini (NotebookLM) no lugar?"):
                ferramenta = "gemini"
                continue
            print(f"\nDepois de resolver, {COMO_REPROCESSAR}.")
            return

        if fonte is not None and resultado.sem_arquivos:
            reenfileiradas = rebaixar_remanescentes(fonte, parametros, resultado.sem_arquivos)
            if reenfileiradas:
                resultado = processar_fila(somente=reenfileiradas, ferramenta=ferramenta)

        if not resultado.falhas:
            if resultado.total:
                print("\nTodos os relatórios foram gerados.")
            return

        mostrar_falhas(resultado, ferramenta)

        if ferramenta == "gemini" and any(_e_erro_de_login(e) for _, e in resultado.falhas) and \
                confirmar("\nDeseja fazer o login no NotebookLM antes de tentar de novo?"):
            fazer_login()

        if not confirmar("\nDeseja tentar gerar os relatórios que falharam agora?"):
            print(f"\nTudo bem. Para tentar depois, {COMO_REPROCESSAR}.")
            return

        ferramenta = escolher_ferramenta(
            f"Tentar de novo com qual ferramenta? (a última foi: {FERRAMENTAS[ferramenta]})"
        )


# ---------------------------------------------------------------------------
# Fluxos
# ---------------------------------------------------------------------------
def fluxo_completo():
    fonte = escolher_fonte()
    parametros = fonte.pedir_parametros()  # data e empresa (perfil)
    # Logo depois da data e da empresa: qual ferramenta vai gerar as análises
    ferramenta = escolher_ferramenta() if ENVIAR_NOTEBOOKLM else None
    licitacoes = fonte.coletar(parametros)

    print(f"\n{len(licitacoes)} licitação(ões) baixada(s).")

    if ENVIAR_NOTEBOOKLM:
        for licitacao in licitacoes:
            enfileirar(licitacao)
        processar_fila_interativo(fonte, parametros, ferramenta)


def menu():
    acoes = {
        OPCAO_COMPLETO: fluxo_completo,
        OPCAO_FILA: processar_fila_interativo,
        OPCAO_LOGIN: fazer_login,
    }
    if CLAUDE_MODO == "assinatura":
        acoes[OPCAO_LOGIN_CLAUDE] = fazer_login_claude
    escolha = pedir_opcao("O que deseja fazer?", list(acoes), confirmar_escolha=False)
    acoes[escolha]()


def main():
    if "--fila" in sys.argv:
        processar_fila_interativo()  # só a fila, sem abrir o navegador
    elif "--login-claude" in sys.argv:
        fazer_login_claude()
    elif "--login" in sys.argv:
        fazer_login()
    else:
        menu()


def _registrar_erro():
    """Guarda o erro inesperado em erro.log (ao lado do programa) para suporte."""
    try:
        with open(BASE_DIR / "erro.log", "a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.now():%d/%m/%Y %H:%M:%S} ---\n{traceback.format_exc()}")
        return BASE_DIR / "erro.log"
    except OSError:
        return None


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrompido pelo usuário.")
    except Exception as erro:
        print(f"\nERRO inesperado: {erro}")
        log = _registrar_erro()
        if log:
            print(f"Os detalhes foram salvos em: {log}")
    finally:
        if EXECUTAVEL:  # no .exe, evita a janela fechar antes de o usuário ler
            input("\nPressione Enter para fechar...")
