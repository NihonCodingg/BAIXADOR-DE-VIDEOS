"""Linha de comando. Usa o MESMO pipeline.py que a web.

    python -m src.cli --perfil edicao_1080 --projeto cliente_x URL
    python -m src.cli --dry-run --perfil edicao_1080 --projeto cliente_x URL

Ticket: T8.
"""

import sys

# Console do Windows é cp1252 e quebra ao imprimir título de vídeo
# (RESEARCH 7.4). Sem isto: UnicodeEncodeError.
sys.stdout.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    raise NotImplementedError("T8")


if __name__ == "__main__":
    sys.exit(main())
