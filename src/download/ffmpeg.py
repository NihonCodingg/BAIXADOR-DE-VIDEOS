"""Detecção do ffmpeg. Toca o sistema de arquivos, por isso não é domínio.

shutil.which e não FFmpegPostProcessor: instantâneo, sem criar processo, sem
depender de API interna do yt-dlp (RESEARCH 5.2). No Windows ele resolve o
.EXE via PATHEXT sozinho — não escrever "ffmpeg.exe" na mão.

Chamar UMA vez, na inicialização. shutil.which toca o disco; não é por job.

Ticket: T1.
"""

import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class StatusFFmpeg:
    ffmpeg: str | None
    ffprobe: str | None

    @property
    def disponivel(self) -> bool:
        return self.ffmpeg is not None

    @property
    def completo(self) -> bool:
        """ffmpeg E ffprobe. Vários postprocessors usam o ffprobe, e ele falta
        com frequência quando alguém copia só um binário para o PATH."""
        return self.ffmpeg is not None and self.ffprobe is not None


def detectar() -> StatusFFmpeg:
    """Procura ffmpeg e ffprobe no PATH, nessa ordem, pelo nome sem sufixo."""
    return StatusFFmpeg(
        ffmpeg=shutil.which("ffmpeg"),
        ffprobe=shutil.which("ffprobe"),
    )
