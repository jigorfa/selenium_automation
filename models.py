"""Estruturas de dados compartilhadas entre as fontes e o pipeline."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Licitacao:
    titulo: str
    pasta: str                  # onde os anexos foram baixados
    fonte: str                  # "effecti", "clickup"...
    data: str | None = None     # "DD/MM/AAAA"
    perfil: str | None = None   # só quando a fonte tiver esse conceito
    prompt: str = "padrao"      # chave em notebooklm/prompts.py
