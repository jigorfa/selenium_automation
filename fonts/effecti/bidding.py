"""Leitura dos favoritos do histórico e download dos anexos (pelo clipe)."""
import time

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from browser.change import aguardar_em_contextos, procurar_em_contextos
from browser.downloads import (
    aguardar_downloads,
    listar_arquivos,
    mover_arquivos_novos,
    pasta_da_licitacao,
)
from fonts.effecti.config import (
    NOME_FONTE,
    PORTAIS_ESPECIAIS,
    PROMPT_POR_PERFIL,
    SELETOR_CLIPE,
    SELETOR_LINKS_MODAL,
    SO_PRIMEIRO_FAVORITO,
    TIMEOUT_MODAL,
)
from models import Licitacao

# Cada licitação na página é uma div "clearfix" dentro de uma "x_title"
CLEARFIX = (By.CLASS_NAME, "clearfix")


def aguardar_licitacoes(driver):
    return aguardar_em_contextos(driver, *CLEARFIX)


def esperar_overlay_sumir(driver, timeout=10):
    try:
        WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, "div.overlay.fullscreen"))
        )
    except TimeoutException:
        pass


def baixar_pelo_clipe(driver, x_title):
    esperar_overlay_sumir(driver)

    botao_anexos = x_title.find_element(By.CSS_SELECTOR, SELETOR_CLIPE)
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_anexos)
    botao_anexos.click()

    modal = WebDriverWait(driver, TIMEOUT_MODAL).until(
        EC.visibility_of_element_located((By.ID, "md-edital-anexo"))
    )

    links = modal.find_elements(By.CSS_SELECTOR, SELETOR_LINKS_MODAL)
    print(f"    Links de download no modal: {len(links)}")

    sucesso = False
    if links:
        arquivos_antes = listar_arquivos()

        for link in links:
            print(f"    Baixando: {link.get_attribute('href')}")
            link.click()
            time.sleep(1)

        baixados = aguardar_downloads(arquivos_antes)
        if baixados:
            print(f"    Download concluído: {baixados}")
            sucesso = True
        else:
            print("    Tempo esgotado aguardando os downloads.")

    try:
        driver.find_element(By.CSS_SELECTOR, "#md-edital-anexo .close").click()
    except NoSuchElementException:
        pass

    esperar_overlay_sumir(driver)
    return sucesso


def processar_licitacoes(driver, data, perfil, coletadas):
    """Baixa os anexos dos favoritos. Cada licitação baixada é adicionada a
    `coletadas` na hora, então um erro no meio não perde as anteriores."""
    clearfixes = driver.find_elements(*CLEARFIX)
    print(f"Total de divs clearfix encontradas: {len(clearfixes)}")
    total = len(clearfixes)
    numero_favorito = 0
    resumo = {"ok": [], "falha": [], "especiais": []}
    prompt = PROMPT_POR_PERFIL.get(perfil, "padrao")

    for indice in range(total):
        # Reencontra os elementos (a troca de janelas pode invalidar a lista/contexto)
        procurar_em_contextos(driver, *CLEARFIX)
        clearfixes = driver.find_elements(*CLEARFIX)
        if indice >= len(clearfixes):
            break
        x_title = clearfixes[indice].find_element(By.XPATH, "..")

        if "x_title" not in (x_title.get_attribute("class") or ""):
            continue

        try:
            titulo = x_title.find_element(By.CSS_SELECTOR, "h2").text.strip()
        except NoSuchElementException:
            titulo = f"(sem título - {indice})"

        favoritado = x_title.find_elements(By.CSS_SELECTOR, 'a[title="Desfavoritar licitação"]')
        if not favoritado:
            print(f"[{indice}] Não favoritado, descartado: {titulo}")
            continue

        print(f"[{indice}] Favoritado: {titulo}")
        numero_favorito += 1

        portal = ""
        try:
            x_panel = x_title.find_element(By.XPATH, "..")
            portal = x_panel.find_element(By.CSS_SELECTOR, "label.title-portal").text.strip()
        except NoSuchElementException:
            pass

        print(f"    Portal: {portal}")

        if portal in PORTAIS_ESPECIAIS:
            print(f"    Portal especial identificado: {portal}")
            resumo["especiais"].append(titulo)
            continue

        pasta = pasta_da_licitacao(NOME_FONTE, data, numero_favorito, titulo)
        arquivos_antes = listar_arquivos()
        baixou = False

        try:
            baixou = baixar_pelo_clipe(driver, x_title)
        except NoSuchElementException:
            print("    Botão de anexos (clipe) não encontrado.")
        except TimeoutException:
            print("    Modal de anexos não abriu a tempo.")

        # O sucesso é decidido pelos arquivos que de fato chegaram na pasta
        aguardar_downloads(arquivos_antes, timeout=90 if baixou else 5, estabilidade=1)
        movidos = mover_arquivos_novos(arquivos_antes, pasta)
        print(f"    {len(movidos)} arquivo(s) movido(s) para: {pasta}")
        for nome in movidos:
            print(f"      - {nome}")

        baixou = bool(movidos)
        if baixou:
            coletadas.append(
                Licitacao(
                    titulo=titulo,
                    pasta=pasta,
                    fonte=NOME_FONTE,
                    data=data,
                    perfil=perfil,
                    prompt=prompt,
                )
            )

        print(f"    Resultado: {'OK' if baixou else 'FALHOU'}")
        resumo["ok" if baixou else "falha"].append(titulo)

        if SO_PRIMEIRO_FAVORITO:
            print("    SO_PRIMEIRO_FAVORITO ativo: encerrando após o primeiro.")
            break

    print("\n===== RESUMO =====")
    print(f"Baixados: {len(resumo['ok'])}")
    print(f"Falharam: {len(resumo['falha'])}")
    for t in resumo["falha"]:
        print(f"   - {t}")
    print(f"Portais especiais (não tratados): {len(resumo['especiais'])}")
    for t in resumo["especiais"]:
        print(f"   - {t}")
