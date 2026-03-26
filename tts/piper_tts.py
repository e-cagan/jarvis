# tts/piper_tts.py
# Piper TTS ile metin → ses dönüşümü.
# ONNX tabanlı, lokal, internetsiz çalışır.
# Metni fonemlere çevirir (espeak-ng), sonra ses dalgası üretir (VITS modeli).

import io
import os
import re
import wave

import numpy as np
import sounddevice as sd
import yaml

from piper import PiperVoice

from tts.base import TTSBase
from utils.logger import setup_logger

logger = setup_logger("piper_tts")


def _load_tts_config():
    """Config'den TTS ayarlarını okur."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config.private.yaml"
    )
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config.get("tts", {})


class PiperTTS(TTSBase):
    """
    Piper tabanlı Text-to-Speech.

    ONNX Runtime üzerinde çalışan VITS modeli.
    Akış: metin → espeak-ng (foneme çevir) → VITS (ses üret) → hoparlör
    """

    def __init__(self):
        config = _load_tts_config()

        # Model yolunu çözümle — config'deki göreceli yol proje kökünden
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model_path = os.path.join(project_root, config.get("model_path", ""))

        self.speech_rate = config.get("speech_rate", 1.0)
        self.speaker_id = config.get("speaker_id", 0)

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Piper model bulunamadı: {model_path}")

        logger.info("Piper model yükleniyor → %s", model_path)

        # PiperVoice modeli ve config'i (.onnx.json) birlikte yükler
        self.voice = PiperVoice.load(model_path)

        # Model config'inden sample rate al
        self.sample_rate = self.voice.config.sample_rate

        logger.info("Piper TTS hazır → %d Hz, hız: %.1fx", self.sample_rate, self.speech_rate)

    def _clean_for_speech(self, text):
        """
        Metni TTS'e göndermeden önce temizler.
        URL'leri, markdown formatlamasını ve gereksiz sembolleri kaldırır.
        LLM yanıtı ekran için formatlanmış olabilir ama kulak için uygun değil.
        """
        # Markdown linkleri: [metin](url) → sadece metin
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

        # Düz URL'leri kaldır
        text = re.sub(r'https?://\S+', '', text)

        # Markdown bold/italic: **metin** veya *metin* → metin
        text = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', text)

        # Markdown code block: ```...``` → kaldır
        text = re.sub(r'```[\s\S]*?```', '', text)

        # Inline code: `metin` → metin
        text = re.sub(r'`([^`]+)`', r'\1', text)

        # Numaralı liste başları: "1. " → ""
        text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)

        # Birden fazla boşluğu teke düşür
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    def speak(self, text):
        """
        Metni sese çevirip hoparlörden çalar.

        Akış:
        1. Piper metin → raw PCM audio üretir
        2. PCM bytes → numpy array dönüşümü
        3. sounddevice ile hoparlöre çal

        Parametreler:
            text (str): Seslendirilecek metin
        """
        if not text or not text.strip():
            logger.warning("Boş metin geldi, atlaniyor")
            return

        # Metni TTS için temizle (URL, markdown vs. kaldır)
        text = self._clean_for_speech(text)

        if not text:
            logger.warning("Temizleme sonrası metin boş kaldı")
            return

        logger.debug("TTS üretiliyor → '%s'", text[:100])

        try:
            # Piper'dan raw PCM audio al
            # synthesize_stream_raw() bir generator — parça parça bytes üretir
            # length_scale konuşma hızını kontrol eder: < 1.0 hızlı, > 1.0 yavaş
            # 1/speech_rate çünkü length_scale ters orantılı (düşük = hızlı)
            # Tek konuşmacılı modellerde speaker_id göndermiyoruz
            # num_speakers config'den okunuyor — 1 ise single speaker
            synth_kwargs = {"length_scale": 1.0 / self.speech_rate}

            if self.voice.config.num_speakers > 1:
                synth_kwargs["speaker_id"] = self.speaker_id

            audio_bytes = b""
            for chunk in self.voice.synthesize_stream_raw(text, **synth_kwargs):
                audio_bytes += chunk

            if not audio_bytes:
                logger.warning("Piper boş audio üretti")
                return

            # Raw PCM bytes → numpy array
            # Piper 16-bit signed integer PCM üretir
            audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0

            # Hoparlöre çal — blocking (ses bitene kadar bekle)
            # Neden blocking? Çünkü ses çalarken kullanıcının yeni komut vermesini
            # beklemek istemiyoruz — önce Jarvis konuşsun, sonra dinlesin
            logger.debug("Ses çalınıyor → %.2f saniye", len(audio_float32) / self.sample_rate)
            sd.play(audio_float32, samplerate=self.sample_rate)
            sd.wait()  # Ses bitene kadar bekle

            logger.debug("TTS tamamlandı")

        except Exception as e:
            logger.error("TTS hatası: %s", e)