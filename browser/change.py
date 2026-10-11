"""Troca de janela/aba e de contexto (iframes)."""
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


def mudar_para_nova_janela(driver, janelas_antes, timeout=10):
    WebDriverWait(driver, timeout).until(
        lambda d: len(d.window_handles) > len(janelas_antes)
    )
    nova_janela = [j for j in driver.window_handles if j not in janelas_antes][0]
    driver.switch_to.window(nova_janela)


def procurar_em_contextos(driver, by, valor):
    """Procura o elemento na página e em até 2 níveis de iframes.
    Se achar, o driver fica posicionado no contexto onde o elemento está."""
    driver.switch_to.default_content()

    if driver.find_elements(by, valor):
        return True

    for frame_1 in driver.find_elements(By.TAG_NAME, "iframe"):
        driver.switch_to.default_content()
        driver.switch_to.frame(frame_1)

        if driver.find_elements(by, valor):
            return True

        for frame_2 in driver.find_elements(By.TAG_NAME, "iframe"):
            driver.switch_to.frame(frame_2)

            if driver.find_elements(by, valor):
                return True

            driver.switch_to.parent_frame()

    return False


def aguardar_em_contextos(driver, by, valor, tentativas=15, intervalo=2):
    for tentativa in range(1, tentativas + 1):
        if procurar_em_contextos(driver, by, valor):
            return True

        print(
            f"Tentativa {tentativa}/{tentativas}: nada encontrado ainda, "
            f"aguardando {intervalo}s..."
        )
        time.sleep(intervalo)

    return False
