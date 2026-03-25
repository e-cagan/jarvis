# tts/base.py
# TTS modülünün abstract interface tanımı.
# Tüm TTS implementasyonları bu class'ı inherit eder.

from abc import ABC, abstractmethod


class TTSBase(ABC):
    """
    Tüm TTS (Text-to-Speech) client'larının uyması gereken sözleşme.
    """

    @abstractmethod
    def speak(self, text):
        """
        Metni sese çevirip hoparlörden çalar.

        Parametreler:
            text (str): Seslendirilecek metin
        """
        pass