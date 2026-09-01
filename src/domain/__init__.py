"""Camada de domínio. PURA.

REGRA DURA 1: este pacote NUNCA importa de src.download, src.storage ou
src.queue. Nada de rede, nada de disco, nada de yt-dlp.

Garantido por tests/test_arquitetura.py.
"""
