"""Projetos: nome legível -> pasta de destino. Puro. SPEC 7.

O domínio valida a ESTRUTURA do YAML (nome, pasta). Se a pasta existe e é
gravável é I/O, e fica com o pipeline.

Ticket: T6.
"""

from dataclasses import dataclass

from .erros import ProjetoInvalido


@dataclass(frozen=True)
class Projeto:
    nome: str        # a chave no YAML; identifica o projeto na API
    rotulo: str      # o `nome:` do YAML; o que a interface mostra
    pasta: str       # destino, sem barra final


def carregar_projetos(dados: dict) -> dict[str, Projeto]:
    """Valida e converte o dicionário lido do YAML. Tudo ou nada.

    Levanta ProjetoInvalido.
    """
    if (not isinstance(dados, dict)
            or not isinstance(dados.get("projetos"), dict)
            or not dados["projetos"]):
        raise ProjetoInvalido(
            "Configuração de projetos vazia ou sem a chave 'projetos'.")

    projetos: dict[str, Projeto] = {}
    for chave, bruto in dados["projetos"].items():
        nome = str(chave)
        if not isinstance(bruto, dict):
            raise ProjetoInvalido(f"Projeto {nome!r}: definição inválida.")
        pasta = bruto.get("pasta")
        if not isinstance(pasta, str) or not pasta.strip():
            raise ProjetoInvalido(f"Projeto {nome!r}: 'pasta' ausente ou vazia.")
        projetos[nome] = Projeto(
            nome=nome,
            rotulo=str(bruto.get("nome") or nome),
            pasta=pasta.strip().rstrip("/\\"),
        )
    return projetos
