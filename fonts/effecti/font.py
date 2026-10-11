"""Fonte Effecti: junta login, navegação e download no contrato de Fonte."""
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from accounts import EFFECTI
from browser.driver import criar_driver
from cli import pedir_data, pedir_opcao
from config import FECHAR_NAVEGADOR
from fonts.base import Fonte
from fonts.effecti.bidding import aguardar_licitacoes, processar_licitacoes
from fonts.effecti.config import NOME_FONTE, PERFIS
from fonts.effecti.session import abrir_historico, fazer_login


class Effecti(Fonte):
    nome = NOME_FONTE

    def pedir_parametros(self):
        return {
            "data": pedir_data(),
            "perfil": pedir_opcao("Perfil de busca", PERFIS),
        }

    def coletar(self, parametros):
        data = parametros["data"]
        perfil = parametros["perfil"]

        if not EFFECTI.get("username") or not EFFECTI.get("password"):
            raise RuntimeError("Preencha usuário e senha do Effecti em accounts.py.")

        licitacoes = []
        driver = criar_driver()

        try:
            fazer_login(driver, EFFECTI["username"], EFFECTI["password"])
            abrir_historico(driver, perfil, data)

            if aguardar_licitacoes(driver):
                processar_licitacoes(driver, data, perfil, licitacoes)
            else:
                print("\nNenhuma licitação encontrada em nenhum contexto.")

            print("\nAutomação finalizada.")

        except TimeoutException as erro:
            print("\nERRO: algum elemento não apareceu dentro do tempo esperado.")
            print(erro)
        except NoSuchElementException as erro:
            print("\nERRO: algum elemento esperado não foi encontrado.")
            print(erro)
        except Exception as erro:
            print(f"\nErro inesperado: {type(erro).__name__}: {erro}")
        finally:
            if FECHAR_NAVEGADOR:
                driver.quit()

        # Mesmo com erro no meio, devolve o que já foi baixado
        return licitacoes
