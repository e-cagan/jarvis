# utils/audio.py
# Mikrofon stream yönetimi ve Voice Activity Detection (VAD).
# Mikrofondan ses alır, VAD ile konuşma algılar, bitince audio verisini döndürür.
# STT modülü bu dosyayı kullanarak "kullanıcı ne zaman konuştu?" sorusunu cevaplar.

import collections
import struct
import time

import numpy as np
import sounddevice as sd
import webrtcvad
import yaml
import os

from utils.logger import setup_logger

logger = setup_logger("audio")


def _load_stt_config():
    """Config'den STT ayarlarını okur."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config.private.yaml"
    )
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config.get("stt", {})


class AudioRecorder:
    """
    Mikrofon erişimi ve VAD tabanlı ses kaydı.

    Akış:
    1. Mikrofon stream'i açılır (16kHz, mono, 16-bit)
    2. Her 30ms'lik frame VAD'a gönderilir
    3. Konuşma algılanınca kayda başlanır
    4. Sessizlik süresi eşiği aşınca kayıt durur
    5. Kaydedilen audio numpy array olarak döndürülür (Whisper'ın beklediği format)
    """

    def __init__(self):
        config = _load_stt_config()

        self.sample_rate = config.get("sample_rate", 16000)
        self.silence_threshold = config.get("silence_threshold", 0.8)

        # VAD ayarları
        # aggressiveness: 0-3 arası, 2 = dengeli
        self.vad = webrtcvad.Vad(2)

        # Frame süresi: 30ms (WebRTC VAD 10/20/30ms destekliyor, 30ms en verimli)
        self.frame_duration_ms = 30

        # 30ms'lik frame'de kaç sample var?
        # 16000 Hz * 0.030 s = 480 sample
        self.frame_size = int(self.sample_rate * self.frame_duration_ms / 1000)

        # Sessizlik sayacı için: kaç frame sessiz olunca "konuşma bitti" deriz?
        # silence_threshold (saniye) / frame_duration (saniye) = frame sayısı
        self.silence_frames_threshold = int(
            self.silence_threshold / (self.frame_duration_ms / 1000)
        )

        # Konuşma başlamadan önceki buffer — konuşmanın başını kaçırmamak için
        # Son 10 frame'i (300ms) her zaman tutuyoruz
        self.pre_speech_buffer_size = 10

        logger.info(
            "AudioRecorder başlatıldı → %d Hz, sessizlik eşiği: %.1fs (%d frame)",
            self.sample_rate, self.silence_threshold, self.silence_frames_threshold
        )

    def listen(self):
        """
        Mikrofonu dinler, konuşma algılayınca kaydeder, bitince döndürür.

        Bu blocking bir çağrı — konuşma bitene kadar bekler.
        Kullanıcı konuşmaya başlayana kadar sessizce dinler (düşük CPU).
        Konuşma bitince numpy array döndürür.

        Dönüş:
            numpy.ndarray: float32 formatında audio verisi, [-1.0, 1.0] aralığında.
                           Whisper bu formatı direkt kabul eder.
            None: Eğer kayıt sırasında hata oluşursa.
        """
        logger.debug("Dinleniyor... (konuşma bekleniyor)")

        # Ring buffer — konuşma başlamadan önceki son N frame'i tutar
        # Böylece konuşmanın ilk hecesi kesilmez
        ring_buffer = collections.deque(maxlen=self.pre_speech_buffer_size)

        # Durum değişkenleri
        is_speaking = False       # Şu anda konuşma algılanıyor mu?
        audio_frames = []         # Kaydedilen tüm frame'ler
        silence_count = 0         # Ardışık sessiz frame sayısı

        try:
            # Mikrofon stream'i aç — blocking modda frame frame okuyacağız
            # dtype='int16' — 16-bit PCM, VAD'ın beklediği format
            # channels=1 — mono
            # blocksize=frame_size — her okumada tam bir VAD frame'i
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                dtype="int16",
                channels=1,
                blocksize=self.frame_size
            ) as stream:

                while True:
                    # Bir frame oku (30ms'lik ses)
                    data, overflowed = stream.read(self.frame_size)

                    if overflowed:
                        logger.warning("Audio buffer overflow — frame atlandı")

                    # data bytes objesi — VAD'a direkt verebiliriz
                    frame_bytes = bytes(data)

                    # VAD ile konuşma kontrolü
                    try:
                        is_speech = self.vad.is_speech(frame_bytes, self.sample_rate)
                    except Exception:
                        # VAD bazen kısa frame'lerde hata verebilir, atla
                        continue

                    if not is_speaking:
                        # Henüz konuşma başlamadı — ring buffer'a ekle
                        ring_buffer.append(frame_bytes)

                        if is_speech:
                            # Konuşma başladı!
                            is_speaking = True
                            silence_count = 0

                            # Ring buffer'daki ön-kayıtları ekle (başı kaçırmamak için)
                            audio_frames.extend(ring_buffer)
                            ring_buffer.clear()

                            logger.debug("Konuşma algılandı — kayıt başladı")

                    else:
                        # Konuşma devam ediyor — her frame'i kaydet
                        audio_frames.append(frame_bytes)

                        if is_speech:
                            silence_count = 0
                        else:
                            silence_count += 1

                            # Yeterince sessizlik oldu mu?
                            if silence_count >= self.silence_frames_threshold:
                                logger.debug(
                                    "Sessizlik algılandı — kayıt durdu (%.1fs ses)",
                                    len(audio_frames) * self.frame_duration_ms / 1000
                                )
                                break

            # Bytes → numpy array dönüşümü
            # frame_bytes'ları birleştirip int16'dan float32'ye çevir
            # Whisper float32 bekliyor, [-1.0, 1.0] aralığında normalize
            raw_audio = b"".join(audio_frames)
            audio_int16 = np.frombuffer(raw_audio, dtype=np.int16)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0  # 16-bit normalize

            logger.info("Ses kaydı tamamlandı → %.2f saniye", len(audio_float32) / self.sample_rate)

            # Çok kısa kayıtları filtrele (0.5 saniyeden kısa = muhtemelen gürültü)
            min_duration = 0.5  # saniye
            if len(audio_float32) / self.sample_rate < min_duration:
                logger.debug("Kayıt çok kısa (%.2fs), atlanıyor", len(audio_float32) / self.sample_rate)
                return None
            
            return audio_float32

        except sd.PortAudioError as e:
            logger.error("Mikrofon erişim hatası: %s", e)
            logger.error("Mikrofon bağlı mı? 'arecord -l' ile kontrol edin.")
            return None

        except Exception as e:
            logger.error("Ses kaydı hatası: %s", e)
            return None