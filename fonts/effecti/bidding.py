"""Leitura dos favoritos do histórico e download dos anexos (pelo clipe)."""
import os
import time

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from browser.change import aguardar_em_contextos, procurar_em_contextos
from browser.direct_download import DownloadDiretoFalhou, baixar_url, criar_sessao, url_baixavel
from browser.downloads import (
    aguardar_downloads,
    listar_arquivos,
    mover_arquivos_novos,
    pasta_da_licitacao,
    remover_arquivos_vazios,
)
from fonts.effecti.config import (
    NOME_FONTE,
    PASTA_POR_PERFIL,
    PORTAIS_ESPECIAIS,
    PROMPT_POR_PERFIL,
    SELETOR_CLIPE,
    SELETOR_LINKS_MODAL,
    SO_PRIMEIRO_FAVORITO,
    TIMEOUT_MODAL,
)
from config import ARQUIVOS_GERADOS, EXTENSAO_PARTE
from models import Licitacao
from notebooklm.queue import carregar_fila

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


# Botões de fechar de pop-ups comuns (modais, avisos, tours). Só clica nos visíveis.
SELETORES_FECHAR_POPUP = [
    ".modal.show .close", ".modal.in .close", ".modal.show [data-dismiss='modal']",
    ".modal.in [data-dismiss='modal']", "button[aria-label='Close']", "button[aria-label='Fechar']",
    "[title='Fechar']", ".swal2-close", ".swal2-confirm", ".introjs-skipbutton",
    ".toast .close", ".notification .close",
]


def fechar_popups(driver):
    """Tenta fechar pop-ups inesperados (alerta do navegador, modais, avisos)."""
    fechou = False
    try:
        driver.switch_to.alert.dismiss()
        fechou = True
    except Exception:
        pass
    try:
        driver.switch_to.active_element.send_keys(Keys.ESCAPE)
    except Exception:
        pass
    for seletor in SELETORES_FECHAR_POPUP:
        try:
            for botao in driver.find_elements(By.CSS_SELECTOR, seletor):
                if botao.is_displayed():
                    driver.execute_script("arguments[0].click();", botao)
                    fechou = True
        except Exception:
            continue
    if fechou:
        print("    Pop-up fechado.")
        time.sleep(1)
    esperar_overlay_sumir(driver, timeout=5)


def ja_baixada(pasta):
    """True se a pasta já tem anexos baixados numa execução anterior."""
    for raiz, _, arquivos in os.walk(pasta):
        for nome in arquivos:
            if (nome in ARQUIVOS_GERADOS or nome.endswith((EXTENSAO_PARTE, ".part"))
                    or nome.startswith("erro_favorito_")):  # print de erro não é anexo
                continue
            if os.path.getsize(os.path.join(raiz, nome)) > 0:
                return True
    return False


def _salvar_print(driver, pasta, indice):
    try:
        caminho = os.path.join(pasta, f"erro_favorito_{indice}.png")
        driver.save_screenshot(caminho)
        print(f"    Print da tela salvo em: {caminho}")
    except Exception:
        pass


def clicar_ignorando_popup(driver, elemento):
    """Clique normal; se um pop-up/overlay estiver na frente, clica via JavaScript.
    O clique por JavaScript dispara o elemento direto, sem depender de ele estar visível
    ou desobstruído."""
    try:
        elemento.click()
    except ElementClickInterceptedException:
        driver.execute_script("arguments[0].click();", elemento)


def baixar_pelo_clipe(driver, x_title):
    """Abre o modal de anexos e baixa os arquivos. Devolve True se algo foi baixado.

    Os links são lidos do HTML (atributo href) e baixados direto com requests, sem clicar:
    um pop-up na frente do link não atrapalha. Se algum link não puder ser baixado assim
    (sem permissão com a sessão do navegador, href que é JavaScript...), ele é clicado
    como antes, deixando o Firefox baixar."""
    esperar_overlay_sumir(driver)

    botao_anexos = x_title.find_element(By.CSS_SELECTOR, SELETOR_CLIPE)
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_anexos)
    clicar_ignorando_popup(driver, botao_anexos)

    modal = WebDriverWait(driver, TIMEOUT_MODAL).until(
        EC.visibility_of_element_located((By.ID, "md-edital-anexo"))
    )

    links = modal.find_elements(By.CSS_SELECTOR, SELETOR_LINKS_MODAL)
    print(f"    Links de download no modal: {len(links)}")

    # Lê os endereços de uma vez, antes de qualquer download (o modal pode mudar depois)
    alvos = [(link, link.get_attribute("href")) for link in links]

    sucesso = False
    if alvos:
        arquivos_antes = listar_arquivos()
        sessao = criar_sessao(driver)
        para_clicar = []

        for indice, (link, href) in enumerate(alvos, 1):
            if not url_baixavel(href):
                para_clicar.append((link, href))
                continue
            print(f"    Baixando: {href}")
            try:
                baixar_url(sessao, href, indice)
            except DownloadDiretoFalhou as erro:
                print(f"      Download direto falhou ({erro}); vou tentar clicando no link.")
                para_clicar.append((link, href))

        for link, href in para_clicar:
            print(f"    Clicando para baixar: {href}")
            driver.execute_script("arguments[0].click();", link)
            time.sleep(1)

        baixados = aguardar_downloads(arquivos_antes)
        if baixados:
            print(f"    Download concluído: {baixados}")
            sucesso = True
        else:
            print("    Tempo esgotado aguardando os downloads.")

    try:
        clicar_ignorando_popup(driver, driver.find_element(By.CSS_SELECTOR, "#md-edital-anexo .close"))
    except NoSuchElementException:
        pass

    esperar_overlay_sumir(driver)
    return sucesso


def processar_licitacoes(driver, data, perfil, coletadas, somente_pastas=None):
    """Baixa os anexos dos favoritos. Cada licitação baixada é adicionada a
    `coletadas` na hora, então um erro no meio não perde as anteriores.

    `somente_pastas` (conjunto de caminhos normalizados): baixa de novo só essas
    licitações (usado por Effecti.rebaixar); None = todas."""
    clearfixes = driver.find_elements(*CLEARFIX)
    print(f"Total de divs clearfix encontradas: {len(clearfixes)}")
    total = len(clearfixes)
    numero_favorito = 0
    resumo = {"ok": [], "falha": [], "especiais": []}
    prompt = PROMPT_POR_PERFIL.get(perfil, "padrao")
    empresa = PASTA_POR_PERFIL.get(perfil, perfil)

    na_fila = set(carregar_fila())  # licitações que já estão na fila (execuções anteriores)

    for indice in range(total):
        # Reencontra os elementos (a troca de janelas pode invalidar a lista/contexto)
        procurar_em_contextos(driver, *CLEARFIX)
        clearfixes = driver.find_elements(*CLEARFIX)
        if indice >= len(clearfixes):
            break
        try:
            x_title = clearfixes[indice].find_element(By.XPATH, "..")
        except Exception:
            continue

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

        pasta = pasta_da_licitacao(NOME_FONTE, data, empresa, numero_favorito, titulo)

        if somente_pastas is not None:
            if os.path.normcase(os.path.abspath(pasta)) not in somente_pastas:
                continue  # baixando de novo só as que ficaram sem arquivo
            remover_arquivos_vazios(pasta)
        elif ja_baixada(pasta):
            # Rodou de novo a mesma data: não baixa outra vez nem refaz o relatório
            print("    Já baixada numa execução anterior; pulando o download.")
            if os.path.abspath(pasta) not in na_fila:
                coletadas.append(Licitacao(titulo=titulo, pasta=pasta, fonte=NOME_FONTE,
                                           data=data, perfil=perfil, prompt=prompt))
            resumo["ok"].append(titulo)
            continue

        arquivos_antes = listar_arquivos()
        baixou = False

        for tentativa in (1, 2):
            try:
                baixou = baixar_pelo_clipe(driver, x_title)
                break
            except NoSuchElementException:
                print("    Botão de anexos (clipe) não encontrado.")
            except TimeoutException:
                print("    Modal de anexos não abriu a tempo.")
            except Exception as erro:  # ex.: pop-up inesperado na frente do botão
                print(f"    Erro neste favorito ({type(erro).__name__}): {str(erro).splitlines()[0][:150]}")
                if tentativa == 1:
                    _salvar_print(driver, pasta, indice)
            # Antes de tentar de novo (ou de seguir para o próximo), tira pop-ups da frente
            fechar_popups(driver)
            if tentativa == 1:
                print("    Tentando este favorito mais uma vez...")
                try:  # o elemento pode ter ficado inválido depois do pop-up
                    procurar_em_contextos(driver, *CLEARFIX)
                    x_title = driver.find_elements(*CLEARFIX)[indice].find_element(By.XPATH, "..")
                except Exception:
                    break

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
