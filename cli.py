"""Interação com o usuário no terminal (genérica, sem nada de site específico)."""
from datetime import datetime


def pedir_inteiro(mensagem, minimo, maximo):
    while True:
        valor = input(mensagem).strip()
        if valor.isdigit() and minimo <= int(valor) <= maximo:
            return int(valor)
        print(f"  Valor inválido. Digite um número entre {minimo} e {maximo}.")


def confirmar(pergunta):
    return input(f"{pergunta} (s/n): ").strip().lower() in ("s", "sim")


def pedir_opcao(titulo, opcoes, confirmar_escolha=True):
    """Mostra uma lista numerada e devolve o texto da opção escolhida."""
    while True:
        print(f"\n=== {titulo} ===")
        for i, nome in enumerate(opcoes, 1):
            print(f"  {i}. {nome}")

        escolha = pedir_inteiro(f"Escolha (1-{len(opcoes)}): ", 1, len(opcoes))
        opcao = opcoes[escolha - 1]

        if not confirmar_escolha or confirmar(f"\nVocê escolheu '{opcao}'. Está correto?"):
            return opcao

        print("Ok, vamos escolher novamente.")


def pedir_data(titulo="Data das licitações"):
    """Pergunta dia, mês e ano, confirma e devolve 'DD/MM/AAAA'."""
    while True:
        print(f"\n=== {titulo} ===")
        dia = pedir_inteiro("Dia: ", 1, 31)
        mes = pedir_inteiro("Mês: ", 1, 12)
        ano = pedir_inteiro("Ano: ", 2000, 2100)

        try:
            data = datetime(ano, mes, dia)
        except ValueError:
            print(f"  A data {dia:02d}/{mes:02d}/{ano} não existe. Tente novamente.")
            continue

        data_str = data.strftime("%d/%m/%Y")
        if confirmar(f"\nVocê digitou {data_str}. Está correto?"):
            return data_str

        print("Ok, vamos digitar a data novamente.")
