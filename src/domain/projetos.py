"""Projetos: nome legível -> pasta de destino. Puro. SPEC 7.

O domínio valida a ESTRUTURA do YAML (nome, pasta). Se a pasta existe e é
gravável é I/O, e fica com o pipeline.

Ticket: T6.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Projeto:
    nome: str        # a chave no YAML; identifica o projeto na API
    rotulo: str      # o `nome:` do YAML; o que a interface mostra
    pasta: str       # destino, sem barra final


def carregar_projetos(dados: dict) -> dict[str, Projeto]:
    """Valida e converte o dicionário lido do YAML. Tudo ou nada.

    Levanta ProjetoInvalido.
    """
    raise NotImplementedError("T6")
