# tools/system/terminal.py
# Shell komutu çalıştıran tool.
# LLM "run_terminal" tool'unu çağırdığında bu fonksiyon tetiklenir.
# Basit bir güvenlik katmanı (blacklist) içerir.

import subprocess

from tools.registry import registry
from utils.logger import setup_logger

logger = setup_logger("terminal")

# Tehlikeli komut pattern'ları — bu stringlerden birini içeren komutlar engellenir
# Kendi makinende çalıştığın için basit bir blacklist yeterli
# İleride whitelist veya user confirmation eklenebilir
BLACKLIST = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs",           # Disk formatlama
    "dd if=",         # Raw disk yazma
    ":(){:|:&};:",    # Fork bomb
    "chmod -R 777 /", # Tüm sisteme full permission
    "shutdown",
    "reboot",
    "init 0",
    "init 6",
]


def _is_safe(command):
    """
    Komutun blacklist'teki tehlikeli pattern'lardan birini içerip içermediğini kontrol eder.

    Dönüş:
        bool: True = güvenli (çalıştırılabilir), False = tehlikeli (engelle)
    """
    command_lower = command.strip().lower()
    for pattern in BLACKLIST:
        if pattern.lower() in command_lower:
            logger.warning("Tehlikeli komut engellendi → %s", command)
            return False
    return True


@registry.register(
    name="run_terminal",
    description="Linux terminal komutu çalıştırır ve çıktısını döndürür. "
                "Dosya listeleme, sistem bilgisi, metin işleme gibi görevler için kullanılır.",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Çalıştırılacak shell komutu (örn: 'ls -la', 'df -h', 'cat dosya.txt')"
            }
        },
        "required": ["command"]
    }
)
def run_terminal(command):
    """
    Verilen shell komutunu çalıştırıp çıktısını döndürür.

    Akış:
    1. Güvenlik kontrolü (blacklist)
    2. subprocess.run ile çalıştır
    3. stdout varsa döndür, yoksa stderr döndür

    Parametreler:
        command (str): Çalıştırılacak shell komutu

    Dönüş:
        str: Komutun stdout çıktısı veya hata mesajı
    """
    # Güvenlik kontrolü
    if not _is_safe(command):
        return "Güvenlik hatası: Bu komut güvenlik politikası tarafından engellendi."

    logger.info("Komut çalıştırılıyor → %s", command)

    try:
        result = subprocess.run(
            command,
            shell=True,          # Shell üzerinden çalıştır (pipe, redirect desteği)
            capture_output=True,  # stdout ve stderr'i yakala
            text=True,           # Çıktıyı bytes değil string olarak döndür
            timeout=30           # 30 saniye sonra öldür (sonsuz döngü koruması)
        )

        # Komut başarılı çalıştıysa stdout, hata varsa stderr döndür
        # returncode 0 = başarılı, diğer = hata
        if result.returncode == 0:
            output = result.stdout.strip()
            # Çıktı çok uzunsa kırp — LLM'e gereksiz yere 10000 satır göndermek istemeyiz
            if len(output) > 5000:
                output = output[:5000] + "\n... (çıktı kırpıldı, toplam karakter: {})".format(len(result.stdout))
            return output if output else "(komut başarılı, çıktı yok)"

        else:
            error = result.stderr.strip()
            return f"Komut hata döndürdü (kod {result.returncode}): {error}"

    except subprocess.TimeoutExpired:
        logger.error("Komut zaman aşımı → %s", command)
        return "Hata: Komut 30 saniye içinde tamamlanamadı."

    except Exception as e:
        logger.error("Komut çalıştırma hatası → %s: %s", command, e)
        return f"Hata: {e}"