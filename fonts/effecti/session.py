"""Login e navegação do Effecti até o histórico de e-mails de um perfil."""
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from browser.change import mudar_para_nova_janela
from fonts.effecti.config import URL_SISTEMA


def fazer_login(driver, usuario, senha, timeout=15):
    wait = WebDriverWait(driver, timeout)

    print("Abrindo Effecti...")
    driver.get(URL_SISTEMA)

    print("Realizando login...")
    campo_usuario = wait.until(EC.presence_of_element_located((By.NAME, "input-login")))
    campo_senha = wait.until(EC.presence_of_element_located((By.NAME, "input-password")))

    campo_usuario.clear()
    campo_usuario.send_keys(usuario)
    campo_senha.clear()
    campo_senha.send_keys(senha)

    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".login-btn"))).click()

    try:
        WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//span[@title='Fechar banner']"))
        ).click()
        print("Banner fechado.")
    except TimeoutException:
        print("Nenhum banner apareceu.")


def _clicar_e_seguir_nova_guia(driver, wait, xpath, descricao):
    janelas_antes = driver.window_handles
    wait.until(EC.element_to_be_clickable((By.XPATH, xpath))).click()

    try:
        mudar_para_nova_janela(driver, janelas_antes, timeout=5)
        print("Nova guia detectada:", driver.current_url)
    except TimeoutException:
        print(f"Nenhuma nova guia após clicar em {descricao}.")


def abrir_historico(driver, perfil, data, timeout=15):
    """Menu Encontrar > perfis > histórico do perfil > linha da data."""
    wait = WebDriverWait(driver, timeout)

    print("Abrindo menu 'Encontrar'...")
    wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(normalize-space(.), 'Encontrar')]")
        )
    ).click()
    wait.until(
        EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, 'avisos-configuracoes')]"))
    ).click()
    wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(@href, 'avisos-configuracoes/perfis')]")
        )
    ).click()

    print(f"Abrindo histórico de {perfil}...")
    xpath_historico = (
        f'//tr[.//span[contains(normalize-space(.), "{perfil}")]]'
        '//button[@title="Histórico de e-mails"]'
    )
    _clicar_e_seguir_nova_guia(driver, wait, xpath_historico, "histórico de e-mails")

    print(f"Procurando histórico de {data}...")
    xpath_data = f'//tr[contains(., "{data}")]//button[@title="Abrir"]'
    _clicar_e_seguir_nova_guia(driver, wait, xpath_data, "Abrir")
