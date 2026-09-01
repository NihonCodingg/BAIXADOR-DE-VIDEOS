"""Back-end web (FastAPI). Só orquestração.

REGRA DURA 2: este pacote NUNCA importa de src.domain. Ele fala com
src.pipeline. Garantido por tests/test_arquitetura.py.
"""
