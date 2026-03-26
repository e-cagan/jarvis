# tools/consolidated/app_control.py
# Birleştirilmiş uygulama yönetim tool'u.

import subprocess
import shutil

from tools.registry import registry
from utils.logger import setup_logger

logger = setup_logger("app_control")

APP_ALIASES = {
    "browser": "firefox", "tarayıcı": "firefox", "firefox": "firefox",
    "chrome": "google-chrome", "chromium": "chromium-browser",
    "dosya yöneticisi": "nautilus", "file manager": "nautilus", "nautilus": "nautilus",
    "text editor": "gedit", "metin editörü": "gedit", "gedit": "gedit",
    "code": "code", "vscode": "code",
    "terminal": "gnome-terminal",
    "vlc": "vlc", "video player": "vlc", "müzik çalar": "vlc",
    "hesap makinesi": "gnome-calculator", "calculator": "gnome-calculator",
    "ayarlar": "gnome-control-center", "settings": "gnome-control-center",
}


def _resolve_app(app_name):
    normalized = app_name.strip().lower()
    binary = APP_ALIASES.get(normalized, normalized)
    installed = shutil.which(binary) is not None
    return binary, installed


@registry.register(
    name="app_control",
    description="Uygulama yönetimi. Desteklenen action'lar: "
                "open (uygulama aç), close (uygulama kapat), list (çalışanları listele). "
                "Bilinen uygulamalar: firefox, chrome, vscode, nautilus, vlc, terminal, gedit.",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Yapılacak işlem: open, close, list"
            },
            "app_name": {
                "type": "string",
                "description": "open ve close için: uygulama adı (örn: firefox, vscode, tarayıcı)"
            }
        },
        "required": ["action"]
    }
)
def app_control(action, app_name=None):
    """Tek fonksiyondan tüm uygulama operasyonları."""
    action = action.lower().strip()

    if action == "open":
        if not app_name:
            return "Hata: 'app_name' parametresi gerekli."
        binary, installed = _resolve_app(app_name)
        if not installed:
            return f"Hata: '{binary}' sistemde bulunamadı."
        try:
            subprocess.Popen([binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            logger.info("Uygulama başlatıldı → %s", binary)
            return f"'{binary}' başlatıldı."
        except Exception as e:
            return f"Hata: {e}"

    elif action == "close":
        if not app_name:
            return "Hata: 'app_name' parametresi gerekli."
        binary, _ = _resolve_app(app_name)
        try:
            result = subprocess.run(["pkill", "-f", binary], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return f"'{binary}' kapatıldı."
            return f"'{binary}' çalışan bulunamadı."
        except Exception as e:
            return f"Hata: {e}"

    elif action == "list":
        try:
            result = subprocess.run(["ps", "-eo", "comm", "--no-headers"], capture_output=True, text=True, timeout=10)
            running = set(result.stdout.strip().split("\n"))
            known = set(APP_ALIASES.values())
            active = [f"  • {app}" for app in sorted(known) if app in running]
            return "Çalışan uygulamalar:\n" + "\n".join(active) if active else "Bilinen uygulamalardan çalışan yok."
        except Exception as e:
            return f"Hata: {e}"

    else:
        return f"Bilinmeyen action: {action}. Geçerli: open, close, list"