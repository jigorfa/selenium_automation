"""Criação do Firefox (igual para qualquer site)."""
import os

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

from config import DOWNLOAD_DIR

TIPOS_BAIXAR_DIRETO = (
    "application/pdf,application/zip,application/x-zip-compressed,"
    "application/octet-stream,application/msword,"
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
    "application/vnd.ms-excel,"
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
    "application/x-rar-compressed"
)


def criar_driver(pasta_download=DOWNLOAD_DIR, headless=False):
    os.makedirs(pasta_download, exist_ok=True)

    options = Options()
    options.set_preference("browser.download.folderList", 2)
    options.set_preference("browser.download.dir", pasta_download)
    options.set_preference("browser.download.useDownloadDir", True)
    options.set_preference("browser.download.manager.showWhenStarting", False)
    options.set_preference("browser.helperApps.neverAsk.saveToDisk", TIPOS_BAIXAR_DIRETO)
    options.set_preference("pdfjs.disabled", True)

    if headless:
        options.add_argument("-headless")

    return webdriver.Firefox(service=Service(), options=options)
