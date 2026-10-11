"""Contrato que toda fonte (site) precisa seguir."""
from abc import ABC, abstractmethod

from models import Licitacao


class Fonte(ABC):
    nome: str

    @abstractmethod
    def pedir_parametros(self) -> dict:
        """Pergunta ao usuário o que esta fonte precisa (data, perfil, filtros...)."""

    @abstractmethod
    def coletar(self, parametros: dict) -> list[Licitacao]:
        """Faz login, navega, baixa os anexos e devolve as licitações baixadas."""
