# tools/system/media.py
# Medya kontrolü — playerctl üzerinden çalışan herhangi bir medya oynatıcıyı kontrol eder.
# Spotify, VLC, Firefox (YouTube) gibi uygulamalar desteklenir.

import subprocess

from tools.registry import registry
from utils.logger import setup_logger

logger = setup_logger("media")


def _run_playerctl(command):
    """playerctl komutu çalıştırır."""
    try:
        result = subprocess.run(
            ["playerctl"] + command.split(),
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip() or "Tamam."
        else:
            return f"Hata: {result.stderr.strip() or 'Aktif medya oynatıcı bulunamadı.'}"
    except FileNotFoundError:
        return "Hata: playerctl kurulu değil. 'sudo apt install playerctl' ile kurun."
    except Exception as e:
        return f"Hata: {e}"


@registry.register(
    name="media_control",
    description="Medya oynatıcıyı kontrol eder: oynat, duraklat, sonraki, önceki, ses seviyesi. "
                "Spotify, VLC, YouTube gibi çalışan medya uygulamalarını kontrol eder.",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Yapılacak işlem: play, pause, next, previous, volume_up, volume_down, status"
            }
        },
        "required": ["action"]
    }
)
def media_control(action):
    """Medya oynatıcıyı kontrol eder."""
    action = action.lower().strip()

    action_map = {
        "play": "play",
        "oynat": "play",
        "pause": "pause",
        "duraklat": "pause",
        "next": "next",
        "sonraki": "next",
        "previous": "previous",
        "önceki": "previous",
        "volume_up": "volume 0.1+",
        "ses_aç": "volume 0.1+",
        "volume_down": "volume 0.1-",
        "ses_kıs": "volume 0.1-",
        "status": "status",
        "durum": "status",
    }

    playerctl_cmd = action_map.get(action)
    if not playerctl_cmd:
        return f"Bilinmeyen işlem: {action}. Geçerli işlemler: play, pause, next, previous, volume_up, volume_down, status"

    logger.info("Medya kontrolü → %s", playerctl_cmd)

    # Status için ek bilgi topla
    if action in ("status", "durum"):
        status = _run_playerctl("status")
        title = _run_playerctl("metadata title")
        artist = _run_playerctl("metadata artist")

        if "Hata" not in status:
            return f"Durum: {status}, Parça: {artist} - {title}"
        return status

    return _run_playerctl(playerctl_cmd)