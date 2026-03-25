# stt/base.py
# STT modülünün abstract interface tanımı.
# Tüm STT implementasyonları bu class'ı inherit eder.

from abc import ABC, abstractmethod


class STTBase(ABC):
    """
    Tüm STT (Speech-to-Text) client'larının uyması gereken sözleşme.
    """

    @abstractmethod
    def transcribe(self, audio):
        """
        Audio verisini metne çevirir.

        Parametreler:
            audio (numpy.ndarray): float32, 16kHz, mono audio verisi

        Dönüş:
            str: Transkripsiyon metni
        """
        pass