# core/event_loop.py
# Ses tabanlı etkileşim döngüsü.
# Dinle → Transkribe → İşle → Seslendir → Tekrarla
# Text modundaki REPL döngüsünün ses versiyonu.

from rich.console import Console

from core.orchestrator import Orchestrator
from stt.whisper_stt import WhisperSTT
from tts.piper_tts import PiperTTS
from utils.audio import AudioRecorder
from utils.logger import setup_logger

logger = setup_logger("event_loop")
console = Console()


class VoiceEventLoop:
    """
    Ses tabanlı Jarvis döngüsü.

    Bileşenler:
    - AudioRecorder: Mikrofon + VAD ile ses kaydı
    - WhisperSTT: Ses → metin
    - Orchestrator: Metin → LLM → Tool → Yanıt
    - PiperTTS: Yanıt → ses

    Döngü her turda:
    1. Kullanıcıyı dinle (VAD ile konuşma algıla)
    2. Sesi metne çevir (Whisper)
    3. Metni işle (Orchestrator — LLM + tool'lar)
    4. Yanıtı seslendir (Piper)
    5. Tekrarla
    """

    def __init__(self):
        console.print("[dim]Bileşenler yükleniyor...[/dim]")

        # Sıra önemli — en uzun süren (Whisper model yükleme) ilk başlasın
        self.stt = WhisperSTT()
        self.tts = PiperTTS()
        self.recorder = AudioRecorder()
        self.orchestrator = Orchestrator()

        logger.info("VoiceEventLoop başlatıldı — tüm bileşenler hazır")

    def run(self):
        """
        Ana ses döngüsünü başlatır.
        Ctrl+C ile çıkılır.
        """
        console.print("\n[bold cyan]Jarvis sesli modda hazır![/bold cyan]")
        console.print("[dim]Konuşmaya başla... (Ctrl+C ile çık)[/dim]\n")

        # Başlangıç selamı
        self._greet()

        while True:
            try:
                # 1. Dinle
                console.print("[dim]Dinliyorum...[/dim]")
                audio = self.recorder.listen()

                if audio is None:
                    logger.warning("Ses kaydı başarısız, tekrar dinleniyor")
                    continue

                # 2. Transkribe et
                text = self.stt.transcribe(audio)

                if not text:
                    logger.debug("Transkripsiyon boş, tekrar dinleniyor")
                    continue

                # Kullanıcının dediğini terminalde göster
                console.print(f"\n[bold green]Sen →[/bold green] {text}")

                # Çıkış komutları (sesli)
                if self._is_exit_command(text):
                    self._farewell()
                    break

                # Sıfırlama komutu
                if self._is_reset_command(text):
                    self.orchestrator.reset()
                    self.tts.speak("Konuşma geçmişi sıfırlandı.")
                    console.print("[dim]Konuşma geçmişi sıfırlandı.[/dim]")
                    continue

                # 3. Orchestrator'a gönder
                response = self.orchestrator.process(text)

                # Yanıtı terminalde göster
                console.print(f"\n[bold cyan]Jarvis →[/bold cyan] {response}")

                # 4. Seslendir
                self.tts.speak(response)

            except KeyboardInterrupt:
                self._farewell()
                break

            except Exception as e:
                logger.error("Döngü hatası: %s", e)
                console.print(f"[bold red]Hata:[/bold red] {e}")

    def _greet(self):
        """Başlangıç selamı."""
        greeting = "Merhaba, ben Jarvis. Seni dinliyorum."
        console.print(f"\n[bold cyan]Jarvis →[/bold cyan] {greeting}")
        self.tts.speak(greeting)

    def _farewell(self):
        """Kapanış selamı."""
        farewell = "Görüşürüz!"
        console.print(f"\n[bold cyan]Jarvis →[/bold cyan] {farewell}")
        self.tts.speak(farewell)

    def _is_exit_command(self, text):
        """
        Transkripsiyon metninin çıkış komutu olup olmadığını kontrol eder.
        Whisper bazen büyük/küçük harf, noktalama ekleyebilir — normalize ediyoruz.
        """
        normalized = text.strip().lower().rstrip(".,!?")
        exit_phrases = [
            "çık", "kapat", "kapan", "görüşürüz",
            "hoşça kal", "kapat jarvis", "çık jarvis",
            "quit", "exit"
        ]
        return normalized in exit_phrases

    def _is_reset_command(self, text):
        """Sıfırlama komutu kontrolü."""
        normalized = text.strip().lower().rstrip(".,!?")
        return normalized in ["sıfırla", "reset", "temizle"]