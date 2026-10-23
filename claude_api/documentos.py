"""Prepara os arquivos da licitação para o Claude (blocos "document" da API).

- PDF com texto: o texto é extraído aqui, com a marcação [Página N] no início de cada
  página (assim o Claude consegue dizer onde está cada informação). Sai bem mais barato
  que mandar o PDF inteiro e cabe muito mais.
- PDF escaneado (páginas sem texto): vai como PDF, e o Claude lê as imagens das páginas.
  Com CLAUDE_ENVIO_PDF = "pdf", todo PDF vai assim.
- DOCX: texto dos parágrafos e das tabelas, na ordem do documento.
- TXT/MD: texto puro.
- O modelo de relatório vai como PDF, com o título "Novo Modelo do Relatório" (é o nome
  que o prompt usa), para o Claude ver a estrutura e a formatação.
- Arquivos repetidos (mesmo conteúdo, nome diferente) são enviados uma vez só.
"""
import base64
import hashlib
import logging
import os
import re
from dataclasses import dataclass, field

from config import CLAUDE_ENVIO_PDF, CLAUDE_MAX_MB_REQUISICAO, CLAUDE_MAX_PAGINAS_PDF

TITULO_MODELO = "Novo Modelo do Relatório"

# Página com menos caracteres que isso é tratada como "sem texto" (escaneada/imagem)
MIN_CARACTERES_PAGINA = 40
# Se esta fração das páginas não tem texto, o PDF vai como PDF (para não perder conteúdo)
FRACAO_SEM_TEXTO = 0.2

# Estimativas grosseiras, só para mostrar o tamanho ao usuário
CARACTERES_POR_TOKEN = 3.5
TOKENS_POR_PAGINA_PDF = 2000

logging.getLogger("pypdf").setLevel(logging.ERROR)  # PDFs de prefeitura vivem dando avisos


class DocumentosInvalidos(RuntimeError):
    """Nenhum arquivo da pasta tem conteúdo que dê para enviar."""


@dataclass
class Pacote:
    """O que vai em cada consulta: blocos da API + números para mostrar ao usuário."""
    blocos: list = field(default_factory=list)
    como_texto: int = 0
    como_pdf: int = 0
    paginas_pdf: int = 0      # páginas enviadas como PDF (limite da API)
    bytes: int = 0            # tamanho aproximado da requisição (limite da API)
    tokens: int = 0           # estimativa
    ignorados: list = field(default_factory=list)  # (arquivo, motivo)
    # Para o modo assinatura (Claude Code), que não recebe PDF pela entrada:
    texto_modelo: str = ""                          # texto do modelo de relatório
    pdfs: list = field(default_factory=list)        # (título, caminho) dos PDFs enviados como PDF

    def resumo(self):
        partes = []
        if self.como_texto:
            partes.append(f"{self.como_texto} como texto")
        if self.como_pdf:
            partes.append(f"{self.como_pdf} como PDF ({self.paginas_pdf} pág.)")
        return (f"{self.como_texto + self.como_pdf} documento(s): {', '.join(partes)}; "
                f"~{_milhar(self.tokens)} tokens estimados")


def _milhar(n):
    return f"{n:,}".replace(",", ".")


def _limpar_texto(texto):
    texto = (texto or "").replace("\x00", "")
    texto = re.sub(r"[ \t]+\n", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _bloco_texto(titulo, texto, contexto=None):
    bloco = {
        "type": "document",
        "source": {"type": "text", "media_type": "text/plain", "data": texto},
        "title": titulo,
    }
    if contexto:
        bloco["context"] = contexto
    return bloco


def _bloco_pdf(titulo, dados, contexto=None):
    bloco = {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": base64.standard_b64encode(dados).decode("ascii"),
        },
        "title": titulo,
    }
    if contexto:
        bloco["context"] = contexto
    return bloco


def _tamanho_base64(n_bytes):
    return 4 * ((n_bytes + 2) // 3)


# ---------------------------------------------------------------------------
# Leitura de cada tipo de arquivo
# ---------------------------------------------------------------------------
def _ler_pdf(dados):
    """Devolve (lista com o texto de cada página, None) ou (None, motivo)."""
    from io import BytesIO

    from pypdf import PdfReader

    try:
        leitor = PdfReader(BytesIO(dados))
        if leitor.is_encrypted:
            try:
                leitor.decrypt("")  # muitos editais têm só "senha de proprietário"
            except Exception:
                return None, "PDF protegido por senha"
        paginas = []
        for pagina in leitor.pages:
            try:
                paginas.append(_limpar_texto(pagina.extract_text()))
            except Exception:
                paginas.append("")  # página com problema: segue com as outras
        return paginas, None
    except Exception as erro:
        return None, f"PDF ilegível ({type(erro).__name__})"


def _texto_docx(caminho):
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(caminho)
    linhas = []
    for elemento in doc.element.body.iterchildren():
        if elemento.tag == qn("w:p"):
            texto = Paragraph(elemento, doc).text.strip()
            if texto:
                linhas.append(texto)
        elif elemento.tag == qn("w:tbl"):
            for linha in Table(elemento, doc).rows:
                celulas = []
                for celula in linha.cells:
                    texto = " ".join(celula.text.split())
                    if not celulas or celulas[-1] != texto:  # célula mesclada repete o texto
                        celulas.append(texto)
                if any(celulas):
                    linhas.append(" | ".join(celulas))
            linhas.append("")
    return _limpar_texto("\n".join(linhas))


def _texto_simples(dados):
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return _limpar_texto(dados.decode(codificacao))
        except UnicodeDecodeError:
            continue
    return ""


# ---------------------------------------------------------------------------
# Montagem
# ---------------------------------------------------------------------------
def _cabe_como_pdf(pacote, paginas, n_bytes):
    limite_bytes = CLAUDE_MAX_MB_REQUISICAO * 1_000_000
    return (pacote.paginas_pdf + paginas <= CLAUDE_MAX_PAGINAS_PDF
            and pacote.bytes + _tamanho_base64(n_bytes) <= limite_bytes)


def _adicionar_pdf(pacote, titulo, dados, paginas, caminho):
    pacote.blocos.append(_bloco_pdf(titulo, dados))
    pacote.pdfs.append((titulo, caminho))
    pacote.como_pdf += 1
    pacote.paginas_pdf += paginas
    pacote.bytes += _tamanho_base64(len(dados))
    pacote.tokens += paginas * TOKENS_POR_PAGINA_PDF


def _adicionar_texto(pacote, titulo, texto, contexto=None):
    pacote.blocos.append(_bloco_texto(titulo, texto, contexto))
    pacote.como_texto += 1
    pacote.bytes += len(texto.encode("utf-8"))
    pacote.tokens += int(len(texto) / CARACTERES_POR_TOKEN)


def _incluir_pdf(pacote, titulo, dados, caminho):
    paginas, motivo = _ler_pdf(dados)
    if paginas is None:
        pacote.ignorados.append((titulo, motivo))
        return
    if not paginas:
        pacote.ignorados.append((titulo, "PDF sem páginas"))
        return

    sem_texto = sum(1 for p in paginas if len(p) < MIN_CARACTERES_PAGINA)
    escaneado = sem_texto / len(paginas) >= FRACAO_SEM_TEXTO
    quer_pdf = CLAUDE_ENVIO_PDF == "pdf" or escaneado

    if quer_pdf and _cabe_como_pdf(pacote, len(paginas), len(dados)):
        _adicionar_pdf(pacote, titulo, dados, len(paginas), caminho)
        return

    if sem_texto == len(paginas):
        pacote.ignorados.append((titulo, "PDF escaneado grande demais para o limite da API "
                                          "(CLAUDE_MAX_PAGINAS_PDF / CLAUDE_MAX_MB_REQUISICAO)"))
        return
    if quer_pdf:
        print(f"      Aviso: {titulo} não cabe como PDF no limite da API; enviando só o texto.")

    texto = "\n\n".join(f"[Página {n}]\n{p}" for n, p in enumerate(paginas, 1))
    contexto = (f"Texto extraído do PDF original ({len(paginas)} página(s)). "
                "A marcação [Página N] indica o início da página N do arquivo.")
    if sem_texto:
        contexto += f" {sem_texto} página(s) sem texto legível (imagem/escaneada)."
    _adicionar_texto(pacote, titulo, texto, contexto)


def montar_pacote(pasta, arquivos, modelo_pdf):
    """Monta os blocos da consulta: modelo do relatório + documentos da licitação."""
    pacote = Pacote()

    with open(modelo_pdf, "rb") as f:
        dados_modelo = f.read()
    paginas_modelo, motivo = _ler_pdf(dados_modelo)
    if paginas_modelo is None:
        raise RuntimeError(f"Não consegui ler o modelo de relatório ({motivo}): {modelo_pdf}")
    pacote.blocos.append(_bloco_pdf(
        TITULO_MODELO, dados_modelo,
        "Modelo do relatório a ser preenchido. NÃO é documento da licitação.",
    ))
    pacote.texto_modelo = "\n\n".join(paginas_modelo)
    pacote.paginas_pdf += len(paginas_modelo)
    pacote.bytes += _tamanho_base64(len(dados_modelo))
    pacote.tokens += len(paginas_modelo) * TOKENS_POR_PAGINA_PDF

    vistos = {}       # hash do conteúdo -> título já enviado
    titulos = set()

    for caminho in arquivos:
        with open(caminho, "rb") as f:
            dados = f.read()
        if not dados:
            pacote.ignorados.append((os.path.basename(caminho), "arquivo vazio (0 bytes)"))
            continue

        assinatura = hashlib.sha256(dados).hexdigest()
        titulo = os.path.basename(caminho)
        if assinatura in vistos:
            print(f"      Ignorando cópia idêntica: {titulo} (igual a {vistos[assinatura]})")
            continue
        if titulo in titulos:  # mesmo nome em subpastas diferentes: usa o caminho
            titulo = os.path.relpath(caminho, pasta).replace(os.sep, "/")
        vistos[assinatura] = titulo
        titulos.add(titulo)

        extensao = os.path.splitext(caminho)[1].lower()
        try:
            if extensao == ".pdf":
                _incluir_pdf(pacote, titulo, dados, caminho)
                continue
            texto = _texto_docx(caminho) if extensao == ".docx" else _texto_simples(dados)
        except Exception as erro:
            pacote.ignorados.append((titulo, f"não consegui ler ({type(erro).__name__}: {erro})"))
            continue

        if texto:
            _adicionar_texto(pacote, titulo, texto)
        else:
            pacote.ignorados.append((titulo, "sem texto"))

    for titulo, motivo in pacote.ignorados:
        print(f"      Aviso: {titulo} não será enviado: {motivo}")

    if len(pacote.blocos) == 1:  # só o modelo
        raise DocumentosInvalidos(
            "Nenhum documento da licitação tem conteúdo legível para o Claude "
            "(veja os avisos acima)."
        )
    return pacote
