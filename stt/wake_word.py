# stt/wake_word.py
# Wake word algılama — "Hey Jarvis" duyulduğunda asistanı aktifleştirir.
# OpenWakeWord kullanır — hafif, CPU'da çalışır, önceden eğitilmiş modeller içerir.
# Whisper'dan ÖNCE çalışır: wake word algılanmadan Whisper tetiklenmez.

import numpy as np
import sounddevice as sd
from openwakeword.model import Model as OWWModel

from utils.logger import setup_logger

logger = setup_logger("wake_word")


class WakeWordDetector:
    """
    Wake word algılayıcı.

    Sürekli mikrofonu dinler, "Hey Jarvis" algıladığında True döner.
    OpenWakeWord modeli CPU'da çalışır — GPU gerektirmez.
    Her 80ms'lik audio chunk'ı modele verir, model olasılık skoru döner.
    Skor eşiği aştığında wake word algılanmış sayılır.
    """

    def __init__(self, threshold=0.5):
        """
        Parametreler:
            threshold (float): Algılama eşiği (0-1 arası).
                Düşük = daha hassas (false positive artar)
                Yüksek = daha katı (bazen algılamaz)
                0.5 dengeli bir başlangıç noktası.
        """
        self.threshold = threshold
        self.sample_rate = 16000

        # OpenWakeWord modelini yükle
        # wakeword_models=["hey_jarvis"] ile sadece hey_jarvis modelini yükle
        # inference_framework="onnx" — ONNX Runtime ile çalışır (hafif, hızlı)
        logger.info("Wake word modeli yükleniyor...")
        self.model = OWWModel(
            wakeword_models=["hey_jarvis"],
            inference_framework="onnx"
        )

        # OpenWakeWord 1280 sample'lık chunk bekliyor (80ms @ 16kHz)
        self.chunk_size = 1280

        logger.info("Wake word algılayıcı hazır → eşik: %.2f", self.threshold)

    def wait_for_wakeword(self):
        """
        Mikrofonu dinler, wake word algılayana kadar bekler.
        Blocking çağrı — wake word duyulana kadar döngüde kalır.

        Dönüş:
            True: Wake word algılandı, asistan aktifleşmeli.
        """
        logger.debug("Wake word bekleniyor ('Hey Jarvis')...")

        # Önceki tahmin skorlarını sıfırla
        self.model.reset()

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self.chunk_size
        ) as stream:

            while True:
                # 80ms'lik chunk oku
                audio_chunk, overflowed = stream.read(self.chunk_size)

                # int16 → float32 → int16 dönüşümü gerekmez
                # OpenWakeWord int16 numpy array kabul ediyor
                audio_array = np.frombuffer(audio_chunk, dtype=np.int16)

                # Modele ver — her chunk için olasılık skoru hesaplar
                prediction = self.model.predict(audio_array)

                # prediction dict: {"hey_jarvis": 0.85, ...}
                for model_name, score in prediction.items():
                    if score >= self.threshold:
                        logger.info("Wake word algılandı! → %s (skor: %.3f)", model_name, score)
                        # Skorları sıfırla — bir sonraki tetikleme için temiz başla
                        self.model.reset()
                        return True