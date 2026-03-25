# tools/system/app_launcher.py
# Uygulama başlatma ve kapatma tool'ları.
# subprocess.Popen ile non-blocking başlatma, pkill ile kapatma.
# Bilinen uygulama alias haritası içerir.

import subprocess
import shutil

from tools.registry import registry
from utils.logger import setup_logger

logger = setup_logger("app_launcher")

# Bilinen uygulama alias haritası
# Kullanıcı veya LLM "browser" dediğinde "firefox" çalıştırılır
# Yeni uygulama eklemek = bu dict'e bir satır eklemek
APP_ALIASES = {
    # Tarayıcılar
    "browser": "firefox",
    "tarayıcı": "firefox",
    "firefox": "firefox",
    "chrome": "google-chrome",
    "chromium": "chromium-browser",

    # Dosya yöneticisi
    "dosya yöneticisi": "nautilus",
    "file manager": "nautilus",
    "nautilus": "nautilus",

    # Metin editörleri
    "text editor": "gedit",
    "metin editörü": "gedit",
    "gedit": "gedit",
    "code": "code",
    "vscode": "code",

    # Terminal
    "terminal": "gnome-terminal",

    # Medya
    "vlc": "vlc",
    "video player": "vlc",
    "müzik çalar": "vlc",

    # Sistem
    "hesap makinesi": "gnome-calculator",
    "calculator": "gnome-calculator",
    "ayarlar": "gnome-control-center",
    "settings": "gnome-control-center",
}


def _resolve_app(app_name):
    """
    Uygulama adını çözümler.

    Önce alias haritasına bakar, bulamazsa orijinal adı döndürür.
    shutil.which() ile binary'nin sistemde kurulu olup olmadığını kontrol eder.
    which() PATH'teki dizinleri tarayıp binary'nin mutlak yolunu döndürür,
    bulamazsa None döner — Linux'taki 'which' komutuyla aynı iş.

    Dönüş:
        tuple: (binary_adı, kurulu_mu)
    """
    # Küçük harfe çevir — alias eşleşmesi case-insensitive olsun
    normalized = app_name.strip().lower()

    # Alias haritasında var mı?
    binary = APP_ALIASES.get(normalized, normalized)

    # Sistemde kurulu mu?
    installed = shutil.which(binary) is not None

    return binary, installed


@registry.register(
    name="open_app",
    description="Bir uygulama başlatır. Uygulama adı veya takma adı ile çalışır "
                "(örn: 'firefox', 'tarayıcı', 'dosya yöneticisi', 'vscode', 'terminal').",
    parameters={
        "type": "object",
        "properties": {
            "app_name": {
                "type": "string",
                "description": "Başlatılacak uygulama adı (örn: 'firefox', 'tarayıcı', 'code', 'nautilus')"
            }
        },
        "required": ["app_name"]
    }
)
def open_app(app_name):
    """Uygulamayı başlatır."""
    binary, installed = _resolve_app(app_name)

    if not installed:
        logger.warning("Uygulama bulunamadı → %s (binary: %s)", app_name, binary)
        return (
            f"Hata: '{binary}' uygulaması sistemde bulunamadı. "
            f"Kurulu olduğundan emin olun veya doğru adını belirtin."
        )

    try:
        # Popen non-blocking — uygulamayı başlatıp hemen döner
        # stdout/stderr DEVNULL'a yönlendiriliyor — uygulama çıktısı Jarvis'i kirletmesin
        # start_new_session=True — uygulama Jarvis'ten bağımsız bir session'da çalışsın
        # Jarvis kapansa bile uygulama açık kalır
        subprocess.Popen(
            [binary],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        logger.info("Uygulama başlatıldı → %s (binary: %s)", app_name, binary)
        return f"'{binary}' uygulaması başlatıldı."

    except Exception as e:
        logger.error("Uygulama başlatma hatası → %s: %s", binary, e)
        return f"Hata: Uygulama başlatılamadı — {e}"


@registry.register(
    name="close_app",
    description="Çalışan bir uygulamayı kapatır. Uygulama adı ile çalışır.",
    parameters={
        "type": "object",
        "properties": {
            "app_name": {
                "type": "string",
                "description": "Kapatılacak uygulama adı (örn: 'firefox', 'vlc', 'code')"
            }
        },
        "required": ["app_name"]
    }
)
def close_app(app_name):
    """Çalışan uygulamayı kapatır."""
    binary, _ = _resolve_app(app_name)

    try:
        # pkill process adına göre SIGTERM gönderir
        # SIGTERM = "düzgünce kapan" sinyali
        # returncode 0 = process bulundu ve sinyal gönderildi
        # returncode 1 = eşleşen process bulunamadı
        result = subprocess.run(
            ["pkill", "-f", binary],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            logger.info("Uygulama kapatıldı → %s", binary)
            return f"'{binary}' uygulaması kapatıldı."
        else:
            return f"'{binary}' adında çalışan bir uygulama bulunamadı."

    except Exception as e:
        logger.error("Uygulama kapatma hatası → %s: %s", binary, e)
        return f"Hata: {e}"


@registry.register(
    name="list_running_apps",
    description="Şu anda çalışan başlıca uygulamaları listeler.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def list_running_apps():
    """Çalışan GUI uygulamalarını listeler."""
    try:
        # wmctrl pencere listesi verir ama her sistemde kurulu olmayabilir
        # ps ile bilinen uygulamaları kontrol etmek daha güvenilir
        result = subprocess.run(
            ["ps", "-eo", "comm", "--no-headers"],
            capture_output=True,
            text=True,
            timeout=10
        )

        running = set(result.stdout.strip().split("\n"))

        # Bilinen uygulamalardan hangilerinin çalıştığını kontrol et
        known_apps = set(APP_ALIASES.values())
        active = []

        for app in sorted(known_apps):
            if app in running:
                active.append(f"  • {app}")

        if active:
            return "Çalışan bilinen uygulamalar:\n" + "\n".join(active)
        else:
            return "Bilinen uygulamalardan şu anda çalışan yok."

    except Exception as e:
        return f"Hata: {e}"