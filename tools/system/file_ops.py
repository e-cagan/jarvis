# tools/system/file_ops.py
# Dosya sistemi operasyonları: oku, yaz, listele, sil, taşı.
# Her operasyon ayrı bir tool olarak registry'ye kaydedilir.
# Güvenlik: Home dizini dışına erişim engellenir.

import os
import shutil

from tools.registry import registry
from utils.logger import setup_logger

logger = setup_logger("file_ops")

# Güvenlik sınırı — bu dizin dışına çıkılamaz
# expanduser("~") → /home/cagan
SAFE_ROOT = os.path.expanduser("~")


def _validate_path(path):
    """
    Verilen yolun güvenli sınırlar içinde olduğunu doğrular.
    Path traversal saldırılarını engeller (../../etc/passwd gibi).

    os.path.realpath() sembolik linkleri ve '..' referanslarını çözer,
    gerçek mutlak yolu döndürür. Bu yolun SAFE_ROOT altında olup
    olmadığını kontrol ediyoruz.

    Parametreler:
        path (str): Kontrol edilecek dosya/dizin yolu

    Dönüş:
        tuple: (bool, str) → (güvenli mi?, gerçek mutlak yol)
    """
    # Göreceli yolu mutlak yola çevir (CWD baz alınır)
    absolute = os.path.realpath(os.path.expanduser(path))

    if not absolute.startswith(SAFE_ROOT):
        logger.warning("Güvenlik ihlali → %s (çözümlenen: %s)", path, absolute)
        return False, absolute

    return True, absolute


@registry.register(
    name="read_file",
    description="Bir dosyanın içeriğini okur ve döndürür. "
                "Metin dosyaları için kullanılır (txt, py, json, yaml, csv, md vb.).",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Okunacak dosyanın yolu (örn: '~/belgeler/notlar.txt', 'config.private.yaml')"
            }
        },
        "required": ["path"]
    }
)
def read_file(path):
    """Dosyayı okuyup içeriğini döndürür."""
    safe, resolved = _validate_path(path)
    if not safe:
        return "Güvenlik hatası: Bu yola erişim izni yok."

    if not os.path.exists(resolved):
        return f"Hata: Dosya bulunamadı → {resolved}"

    if not os.path.isfile(resolved):
        return f"Hata: Bu bir dosya değil, dizin → {resolved}"

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            content = f.read()

        # Çok uzun dosyaları kırp — LLM context window'unu korumak için
        if len(content) > 10000:
            content = content[:10000] + f"\n\n... (kırpıldı, toplam {len(content)} karakter)"

        logger.info("Dosya okundu → %s (%d karakter)", resolved, len(content))
        return content

    except UnicodeDecodeError:
        return "Hata: Bu bir metin dosyası değil (binary dosya okunamaz)."
    except Exception as e:
        return f"Hata: {e}"


@registry.register(
    name="write_file",
    description="Bir dosyaya içerik yazar. Dosya yoksa oluşturur, varsa üzerine yazar. "
                "Yeni dosya oluşturmak veya mevcut dosyayı güncellemek için kullanılır.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Yazılacak dosyanın yolu (örn: '~/belgeler/not.txt', 'test.py')"
            },
            "content": {
                "type": "string",
                "description": "Dosyaya yazılacak içerik"
            }
        },
        "required": ["path", "content"]
    }
)
def write_file(path, content):
    """Dosyaya içerik yazar. Yoksa oluşturur, varsa üzerine yazar."""
    safe, resolved = _validate_path(path)
    if not safe:
        return "Güvenlik hatası: Bu yola erişim izni yok."

    try:
        # Ara dizinler yoksa oluştur
        # Örn: ~/belgeler/yeni_klasor/dosya.txt → yeni_klasor otomatik oluşur
        os.makedirs(os.path.dirname(resolved), exist_ok=True)

        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("Dosya yazıldı → %s (%d karakter)", resolved, len(content))
        return f"Dosya başarıyla yazıldı → {resolved}"

    except Exception as e:
        return f"Hata: {e}"


@registry.register(
    name="list_directory",
    description="Bir dizindeki dosya ve klasörleri listeler. "
                "Boyut ve değiştirilme tarihi bilgisiyle birlikte döndürür.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Listelenecek dizin yolu (örn: '~', '~/belgeler', '.')"
            }
        },
        "required": ["path"]
    }
)
def list_directory(path):
    """Dizindeki dosya ve klasörleri detaylı listeler."""
    safe, resolved = _validate_path(path)
    if not safe:
        return "Güvenlik hatası: Bu yola erişim izni yok."

    if not os.path.isdir(resolved):
        return f"Hata: Dizin bulunamadı → {resolved}"

    try:
        entries = os.listdir(resolved)
        entries.sort()

        lines = []
        for entry in entries:
            full_path = os.path.join(resolved, entry)

            if os.path.isdir(full_path):
                lines.append(f"  [DIR]  {entry}/")
            else:
                # Dosya boyutunu human-readable formata çevir
                size = os.path.getsize(full_path)
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                lines.append(f"  [FILE] {entry} ({size_str})")

        result = f"Dizin: {resolved}\n{'─' * 40}\n" + "\n".join(lines)
        logger.info("Dizin listelendi → %s (%d öğe)", resolved, len(entries))
        return result

    except PermissionError:
        return f"Hata: Bu dizine erişim izni yok → {resolved}"
    except Exception as e:
        return f"Hata: {e}"


@registry.register(
    name="delete_file",
    description="Bir dosya veya boş dizini siler. Dolu dizinleri silmez (güvenlik).",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Silinecek dosya veya dizin yolu"
            }
        },
        "required": ["path"]
    }
)
def delete_file(path):
    """Dosya veya boş dizin siler."""
    safe, resolved = _validate_path(path)
    if not safe:
        return "Güvenlik hatası: Bu yola erişim izni yok."

    if not os.path.exists(resolved):
        return f"Hata: Dosya/dizin bulunamadı → {resolved}"

    try:
        if os.path.isfile(resolved):
            os.remove(resolved)
            logger.info("Dosya silindi → %s", resolved)
            return f"Dosya silindi → {resolved}"

        elif os.path.isdir(resolved):
            # Sadece boş dizin silinir — güvenlik kararı
            # Dolu dizin silmek tehlikeli, kullanıcı farkında olmayabilir
            os.rmdir(resolved)
            logger.info("Dizin silindi → %s", resolved)
            return f"Dizin silindi → {resolved}"

    except OSError as e:
        if "not empty" in str(e).lower() or "dizin boş değil" in str(e).lower():
            return "Hata: Dizin boş değil. Güvenlik nedeniyle dolu dizinler silinmez."
        return f"Hata: {e}"
    except Exception as e:
        return f"Hata: {e}"


@registry.register(
    name="move_file",
    description="Bir dosya veya dizini başka bir konuma taşır veya yeniden adlandırır.",
    parameters={
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Taşınacak dosya/dizin yolu"
            },
            "destination": {
                "type": "string",
                "description": "Hedef yol"
            }
        },
        "required": ["source", "destination"]
    }
)
def move_file(source, destination):
    """Dosya/dizini taşır veya yeniden adlandırır."""
    safe_src, resolved_src = _validate_path(source)
    safe_dst, resolved_dst = _validate_path(destination)

    if not safe_src or not safe_dst:
        return "Güvenlik hatası: Kaynak veya hedef yola erişim izni yok."

    if not os.path.exists(resolved_src):
        return f"Hata: Kaynak bulunamadı → {resolved_src}"

    try:
        shutil.move(resolved_src, resolved_dst)
        logger.info("Taşındı → %s → %s", resolved_src, resolved_dst)
        return f"Taşındı: {resolved_src} → {resolved_dst}"

    except Exception as e:
        return f"Hata: {e}"


@registry.register(
    name="copy_file",
    description="Bir dosya veya dizini başka bir konuma kopyalar.",
    parameters={
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Kopyalanacak dosya/dizin yolu"
            },
            "destination": {
                "type": "string",
                "description": "Hedef yol"
            }
        },
        "required": ["source", "destination"]
    }
)
def copy_file(source, destination):
    """Dosya veya dizini kopyalar."""
    safe_src, resolved_src = _validate_path(source)
    safe_dst, resolved_dst = _validate_path(destination)

    if not safe_src or not safe_dst:
        return "Güvenlik hatası: Kaynak veya hedef yola erişim izni yok."

    if not os.path.exists(resolved_src):
        return f"Hata: Kaynak bulunamadı → {resolved_src}"

    try:
        if os.path.isdir(resolved_src):
            # Dizin kopyalama — shutil.copytree hedef dizin olmamalı
            shutil.copytree(resolved_src, resolved_dst)
        else:
            # Hedef dizin yoksa oluştur
            os.makedirs(os.path.dirname(resolved_dst), exist_ok=True)
            shutil.copy2(resolved_src, resolved_dst)

        logger.info("Kopyalandı → %s → %s", resolved_src, resolved_dst)
        return f"Kopyalandı: {resolved_src} → {resolved_dst}"

    except Exception as e:
        return f"Hata: {e}"


@registry.register(
    name="append_to_file",
    description="Bir dosyanın sonuna içerik ekler. Dosya yoksa oluşturur. "
                "Not ekleme, log tutma gibi işlemler için kullanılır.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "İçerik eklenecek dosyanın yolu"
            },
            "content": {
                "type": "string",
                "description": "Dosyanın sonuna eklenecek içerik"
            }
        },
        "required": ["path", "content"]
    }
)
def append_to_file(path, content):
    """Dosyanın sonuna içerik ekler. Yoksa oluşturur."""
    safe, resolved = _validate_path(path)
    if not safe:
        return "Güvenlik hatası: Bu yola erişim izni yok."

    try:
        os.makedirs(os.path.dirname(resolved), exist_ok=True)

        with open(resolved, "a", encoding="utf-8") as f:
            f.write(content)

        logger.info("Dosyaya eklendi → %s (%d karakter)", resolved, len(content))
        return f"İçerik dosyaya eklendi → {resolved}"

    except Exception as e:
        return f"Hata: {e}"