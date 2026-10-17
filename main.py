"""Ponto de entrada: escolhe a fonte, coleta as licitações e manda para o NotebookLM.

Uso:
    python main.py          # menu (ou duplo clique no .exe)
    python main.py --fila   # só processa a fila do NotebookLM (sem abrir navegador)
    python main.py --login  # só faz o login no NotebookLM
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
from config import BASE_DIR, COMO_REPROCESSAR, ENVIAR_NOTEBOOKLM, EXECUTAVEL
from fonts import FONTES
from notebooklm.client import ERROS_DE_LOGIN, erro_passageiro, login_nlm
from notebooklm.processor import processar_fila
from notebooklm.queue import carregar_fila, enfileirar, salvar_fila

OPCAO_COMPLETO = "Baixar licitações e gerar relatórios (fluxo completo)"
OPCAO_FILA = "Processar a fila de relatórios pendentes (sem baixar nada)"
OPCAO_LOGIN = "Fazer login no NotebookLM"


def escolher_fonte():
    nomes = list(FONTES)
    if len(nomes) == 1:  # só uma fonte cadastrada: não precisa perguntar
        return FONTES[nomes[0]]()

    nome = pedir_opcao("Fonte de licitações", nomes, confirmar_escolha=False)
    return FONTES[nome]()


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


def mostrar_falhas(resultado):
    """Lista os relatórios que NÃO foram gerados e diz o que fazer."""
    falhas = resultado.falhas
    print("\n" + "=" * 60)
    print(f"ATENÇÃO: {len(falhas)} relatório(s) NÃO foram gerados "
          f"({resultado.concluidos} de {resultado.total} concluídos):")
    for nome, erro in falhas:
        print(f"  - {nome}")
        print(f"      motivo: {_resumir_erro(erro)}")

    print("\nO que fazer:")
    if any(_e_erro_de_login(e) for _, e in falhas):
        print("  * Parece problema de LOGIN no NotebookLM: refaça o login e tente de novo.")
    if all(erro_passageiro(RuntimeError(e)) for _, e in falhas):
        print("  * O NotebookLM não respondeu. Costuma ser instabilidade ou o limite diário de consultas.")
        print("    Tentar de novo agora às vezes funciona; se falhar outra vez, espere de 30 a 60 minutos")
        print("    ou tente amanhã. O que já foi respondido fica salvo e não é refeito.")
    if any("Nenhum arquivo compatível" in e for _, e in falhas):
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


def processar_fila_interativo(fonte=None, parametros=None):
    """Processa a fila; se algo falhar, explica e pergunta se quer tentar de novo agora.

    Com `fonte` e `parametros` (fluxo completo), as licitações que ficaram sem arquivo
    utilizável voltam ao download uma vez, ao fim da fila, e são processadas de novo."""
    while True:
        resultado = processar_fila()

        if resultado.motivo_parada == "sem_modelo":
            return

        if resultado.motivo_parada == "sem_login":
            print("\nNão foi possível acessar o NotebookLM (provavelmente o login venceu ou não foi feito).")
            if confirmar("Deseja fazer o login no NotebookLM agora?"):
                fazer_login()
                continue
            print(f"\nQuando fizer o login, {COMO_REPROCESSAR}.")
            return

        if fonte is not None and resultado.sem_arquivos:
            reenfileiradas = rebaixar_remanescentes(fonte, parametros, resultado.sem_arquivos)
            if reenfileiradas:
                resultado = processar_fila(somente=reenfileiradas)

        if not resultado.falhas:
            if resultado.total:
                print("\nTodos os relatórios foram gerados.")
            return

        mostrar_falhas(resultado)

        if any(_e_erro_de_login(e) for _, e in resultado.falhas) and \
                confirmar("\nDeseja fazer o login no NotebookLM antes de tentar de novo?"):
            fazer_login()

        if not confirmar("\nDeseja tentar gerar os relatórios que falharam agora?"):
            print(f"\nTudo bem. Para tentar depois, {COMO_REPROCESSAR}.")
            return


# ---------------------------------------------------------------------------
# Fluxos
# ---------------------------------------------------------------------------
def fluxo_completo():
    fonte = escolher_fonte()
    parametros = fonte.pedir_parametros()
    licitacoes = fonte.coletar(parametros)

    print(f"\n{len(licitacoes)} licitação(ões) baixada(s).")

    if ENVIAR_NOTEBOOKLM:
        for licitacao in licitacoes:
            enfileirar(licitacao)
        processar_fila_interativo(fonte, parametros)


def menu():
    acoes = {
        OPCAO_COMPLETO: fluxo_completo,
        OPCAO_FILA: processar_fila_interativo,
        OPCAO_LOGIN: fazer_login,
    }
    escolha = pedir_opcao("O que deseja fazer?", list(acoes), confirmar_escolha=False)
    acoes[escolha]()


def main():
    if "--fila" in sys.argv:
        processar_fila_interativo()  # só a fila, sem abrir o navegador
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
