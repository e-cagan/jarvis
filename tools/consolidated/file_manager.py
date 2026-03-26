# tools/consolidated/file_manager.py
# Birleştirilmiş dosya yönetim tool'u.
# 7 ayrı tool yerine tek tool, action parametresiyle.

import os
import shutil

from tools.registry import registry
from utils.logger import setup_logger

logger = setup_logger("file_manager")

SAFE_ROOT = os.path.expanduser("~")


def _validate_path(path):
    """Home dizini dışına erişimi engeller."""
    absolute = os.path.realpath(os.path.expanduser(path))
    if not absolute.startswith(SAFE_ROOT):
        logger.warning("Güvenlik ihlali → %s", path)
        return False, absolute
    return True, absolute


@registry.register(
    name="file_manager",
    description="Dosya ve dizin yönetimi. Desteklenen action'lar: "
                "read (dosya oku), write (dosya yaz/oluştur), append (dosya sonuna ekle), "
                "list (dizin listele), delete (dosya/dizin sil), move (taşı/yeniden adlandır), "
                "copy (kopyala).",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Yapılacak işlem: read, write, append, list, delete, move, copy"
            },
            "path": {
                "type": "string",
                "description": "Hedef dosya veya dizin yolu"
            },
            "content": {
                "type": "string",
                "description": "write ve append için: yazılacak içerik"
            },
            "destination": {
                "type": "string",
                "description": "move ve copy için: hedef yol"
            }
        },
        "required": ["action", "path"]
    }
)
def file_manager(action, path, content=None, destination=None):
    """Tek fonksiyondan tüm dosya operasyonları."""
    action = action.lower().strip()

    if action == "read":
        safe, resolved = _validate_path(path)
        if not safe:
            return "Güvenlik hatası: Bu yola erişim izni yok."
        if not os.path.isfile(resolved):
            return f"Hata: Dosya bulunamadı → {resolved}"
        try:
            with open(resolved, "r", encoding="utf-8") as f:
                text = f.read()
            if len(text) > 10000:
                text = text[:10000] + f"\n... (kırpıldı, toplam {len(text)} karakter)"
            logger.info("Dosya okundu → %s", resolved)
            return text
        except UnicodeDecodeError:
            return "Hata: Binary dosya okunamaz."
        except Exception as e:
            return f"Hata: {e}"

    elif action == "write":
        if content is None:
            return "Hata: 'content' parametresi gerekli."
        safe, resolved = _validate_path(path)
        if not safe:
            return "Güvenlik hatası: Bu yola erişim izni yok."
        try:
            os.makedirs(os.path.dirname(resolved), exist_ok=True)
            with open(resolved, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("Dosya yazıldı → %s", resolved)
            return f"Dosya yazıldı → {resolved}"
        except Exception as e:
            return f"Hata: {e}"

    elif action == "append":
        if content is None:
            return "Hata: 'content' parametresi gerekli."
        safe, resolved = _validate_path(path)
        if not safe:
            return "Güvenlik hatası: Bu yola erişim izni yok."
        try:
            os.makedirs(os.path.dirname(resolved), exist_ok=True)
            with open(resolved, "a", encoding="utf-8") as f:
                f.write(content)
            logger.info("Dosyaya eklendi → %s", resolved)
            return f"İçerik eklendi → {resolved}"
        except Exception as e:
            return f"Hata: {e}"

    elif action == "list":
        safe, resolved = _validate_path(path)
        if not safe:
            return "Güvenlik hatası: Bu yola erişim izni yok."
        if not os.path.isdir(resolved):
            return f"Hata: Dizin bulunamadı → {resolved}"
        try:
            entries = sorted(os.listdir(resolved))
            lines = []
            for entry in entries:
                full = os.path.join(resolved, entry)
                if os.path.isdir(full):
                    lines.append(f"  [DIR]  {entry}/")
                else:
                    size = os.path.getsize(full)
                    size_str = f"{size} B" if size < 1024 else f"{size/1024:.1f} KB" if size < 1048576 else f"{size/1048576:.1f} MB"
                    lines.append(f"  [FILE] {entry} ({size_str})")
            return f"Dizin: {resolved}\n" + "\n".join(lines)
        except Exception as e:
            return f"Hata: {e}"

    elif action == "delete":
        safe, resolved = _validate_path(path)
        if not safe:
            return "Güvenlik hatası: Bu yola erişim izni yok."
        if not os.path.exists(resolved):
            return f"Hata: Bulunamadı → {resolved}"
        try:
            if os.path.isfile(resolved):
                os.remove(resolved)
            elif os.path.isdir(resolved):
                os.rmdir(resolved)
            logger.info("Silindi → %s", resolved)
            return f"Silindi → {resolved}"
        except OSError:
            return "Hata: Dizin boş değil. Dolu dizinler silinmez."
        except Exception as e:
            return f"Hata: {e}"

    elif action == "move":
        if destination is None:
            return "Hata: 'destination' parametresi gerekli."
        safe_s, res_s = _validate_path(path)
        safe_d, res_d = _validate_path(destination)
        if not safe_s or not safe_d:
            return "Güvenlik hatası: Erişim izni yok."
        if not os.path.exists(res_s):
            return f"Hata: Kaynak bulunamadı → {res_s}"
        try:
            shutil.move(res_s, res_d)
            logger.info("Taşındı → %s → %s", res_s, res_d)
            return f"Taşındı: {res_s} → {res_d}"
        except Exception as e:
            return f"Hata: {e}"

    elif action == "copy":
        if destination is None:
            return "Hata: 'destination' parametresi gerekli."
        safe_s, res_s = _validate_path(path)
        safe_d, res_d = _validate_path(destination)
        if not safe_s or not safe_d:
            return "Güvenlik hatası: Erişim izni yok."
        if not os.path.exists(res_s):
            return f"Hata: Kaynak bulunamadı → {res_s}"
        try:
            if os.path.isdir(res_s):
                shutil.copytree(res_s, res_d)
            else:
                os.makedirs(os.path.dirname(res_d), exist_ok=True)
                shutil.copy2(res_s, res_d)
            logger.info("Kopyalandı → %s → %s", res_s, res_d)
            return f"Kopyalandı: {res_s} → {res_d}"
        except Exception as e:
            return f"Hata: {e}"

    else:
        return f"Bilinmeyen action: {action}. Geçerli: read, write, append, list, delete, move, copy"