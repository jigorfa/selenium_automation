"""Ponto de entrada: escolhe a fonte, coleta as licitações e manda para o NotebookLM.

Uso:
    python main.py          # fluxo completo
    python main.py --fila   # só processa a fila do NotebookLM (sem abrir navegador)
"""
import sys

from cli import pedir_opcao
from config import ENVIAR_NOTEBOOKLM
from fonts import FONTES
from notebooklm.processor import processar_fila
from notebooklm.queue import enfileirar


def escolher_fonte():
    nomes = list(FONTES)
    if len(nomes) == 1:  # só uma fonte cadastrada: não precisa perguntar
        return FONTES[nomes[0]]()

    nome = pedir_opcao("Fonte de licitações", nomes, confirmar_escolha=False)
    return FONTES[nome]()


def main():
    fonte = escolher_fonte()
    parametros = fonte.pedir_parametros()
    licitacoes = fonte.coletar(parametros)

    print(f"\n{len(licitacoes)} licitação(ões) baixada(s).")

    if ENVIAR_NOTEBOOKLM:
        for licitacao in licitacoes:
            enfileirar(licitacao)
        processar_fila()


if __name__ == "__main__":
    if "--fila" in sys.argv:
        processar_fila()  # só a fila, sem abrir o navegador
    else:
        main()
