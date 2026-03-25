# stt/whisper_stt.py
# faster-whisper ile Speech-to-Text implementasyonu.
# CTranslate2 optimize Whisper — GPU'da float16 ile çok hızlı inference.
# İlk çağrıda model indirilir ve bellekte kalır.

import os
import yaml

from faster_whisper import WhisperModel

from stt.base import STTBase
from utils.logger import setup_logger

logger = setup_logger("whisper_stt")


def _load_stt_config():
    """Config'den STT ayarlarını okur."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config.yaml"
    )
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config.get("stt", {})


class WhisperSTT(STTBase):
    """
    faster-whisper tabanlı Speech-to-Text.

    İlk instantiation'da model indirilir (bir kez, sonra cache'lenir).
    GPU varsa CUDA + float16 kullanır — çok hızlı.
    CPU'da int8 quantization ile çalışır — yavaş ama kullanılabilir.
    """

    def __init__(self):
        config = _load_stt_config()

        self.model_size = config.get("model_size", "medium")
        self.language = config.get("language", "tr")
        self.device = config.get("device", "cuda")
        self.compute_type = config.get("compute_type", "float16")

        logger.info(
            "Whisper model yükleniyor → %s (%s, %s)...",
            self.model_size, self.device, self.compute_type
        )

        # Model yükleme — ilk seferde indirilir (~1-3 GB model boyutuna göre)
        # Sonraki çalıştırmalarda cache'den yüklenir (~/.cache/huggingface/)
        self.model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type
        )

        logger.info("Whisper model hazır → %s", self.model_size)

    def transcribe(self, audio):
        """
        Audio verisini metne çevirir.

        Parametreler:
            audio (numpy.ndarray): float32, 16kHz, mono audio verisi
                                   AudioRecorder.listen()'den gelen format.

        Dönüş:
            str: Transkripsiyon metni. Boş string eğer ses algılanamazsa.
        """
        if audio is None or len(audio) == 0:
            logger.warning("Boş audio verisi geldi")
            return ""

        logger.debug("Transkripsiyon başlıyor → %.2f saniye ses", len(audio) / 16000)

        try:
            # transcribe() bir generator döndürür — (segments, info) tuple'ı
            # language="tr" ile dil algılama adımı atlanır → hız kazancı
            # beam_size=5 → standart doğruluk/hız dengesi
            # vad_filter=True → sessiz kısımları atla, hallucination azalt
            segments, info = self.model.transcribe(
                audio,
                language=self.language,
                beam_size=5,
                vad_filter=True
            )

            # Segment'leri birleştir
            # Her segment bir cümle veya cümle parçası — text alanını alıyoruz
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())

            full_text = " ".join(text_parts).strip()

            if full_text:
                logger.info("Transkripsiyon → '%s'", full_text)
            else:
                logger.warning("Transkripsiyon boş döndü (ses çok kısa veya anlaşılmaz olabilir)")

            return full_text

        except Exception as e:
            logger.error("Transkripsiyon hatası: %s", e)
            return ""