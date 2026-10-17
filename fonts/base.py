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

    def rebaixar(self, parametros: dict, pastas: list[str]) -> list[Licitacao]:
        """Baixa de novo os anexos só das licitações cujas pastas foram indicadas.

        Usado quando uma licitação ficou sem nenhum arquivo utilizável (ex.: download vazio).
        Fontes que não suportam isso devolvem lista vazia."""
        print(f"    A fonte '{self.nome}' não suporta baixar de novo.")
        return []
