# core/plugin_loader.py
# Dinamik plugin keşif ve yükleme sistemi.
# plugins/ dizinindeki .py dosyalarını otomatik bulur ve import eder.
# Import sırasında @registry.register decorator'ları çalışır → tool'lar kaydolur.
# main.py'ye import eklemeye gerek kalmaz.

import os
import sys
import importlib
import importlib.util

from utils.logger import setup_logger

logger = setup_logger("plugin_loader")

# Plugin dizini — proje kökünde
PLUGIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "plugins"
)


class PluginLoader:
    """
    Dinamik plugin yükleme sistemi.

    Akış:
    1. plugins/ dizinini tara
    2. Her .py dosyasını importlib ile yükle
    3. @registry.register decorator'ları otomatik çalışır
    4. Plugin metadata'sı (varsa) toplanır

    Metadata (opsiyonel): Plugin dosyasının başında PLUGIN_INFO dict'i tanımlanabilir:
        PLUGIN_INFO = {
            "name": "Hava Durumu",
            "version": "1.0",
            "author": "Çağan",
            "description": "Detaylı hava durumu bilgisi"
        }
    """

    def __init__(self):
        self.loaded_plugins = {}  # {dosya_adı: metadata}
        self.errors = {}          # {dosya_adı: hata_mesajı}

    def discover_and_load(self):
        """
        plugins/ dizinini tarar ve tüm .py dosyalarını yükler.

        Dönüş:
            int: Başarıyla yüklenen plugin sayısı
        """
        # Dizin yoksa oluştur
        if not os.path.exists(PLUGIN_DIR):
            os.makedirs(PLUGIN_DIR, exist_ok=True)
            # Boş __init__.py oluştur
            init_path = os.path.join(PLUGIN_DIR, "__init__.py")
            if not os.path.exists(init_path):
                with open(init_path, "w") as f:
                    f.write("# Jarvis plugins directory\n")
            logger.info("Plugin dizini oluşturuldu → %s", PLUGIN_DIR)
            return 0

        # plugins/ dizinini Python path'e ekle (import için)
        if PLUGIN_DIR not in sys.path:
            sys.path.insert(0, PLUGIN_DIR)

        # Proje kökünü de path'e ekle (plugin'ler tools.registry'yi import edebilsin)
        project_root = os.path.dirname(PLUGIN_DIR)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        # .py dosyalarını bul
        plugin_files = []
        for filename in sorted(os.listdir(PLUGIN_DIR)):
            if filename.endswith(".py") and not filename.startswith("_"):
                plugin_files.append(filename)

        if not plugin_files:
            logger.info("Plugin bulunamadı → %s", PLUGIN_DIR)
            return 0

        # Her dosyayı yükle
        loaded_count = 0
        for filename in plugin_files:
            success = self._load_plugin(filename)
            if success:
                loaded_count += 1

        logger.info(
            "Plugin yükleme tamamlandı → %d/%d başarılı",
            loaded_count, len(plugin_files)
        )

        return loaded_count

    def _load_plugin(self, filename):
        """
        Tek bir plugin dosyasını yükler.

        importlib.util.spec_from_file_location() ile dosya yolundan
        modül spec'i oluşturulur, sonra module_from_spec() ile modül
        objesi yaratılır ve exec_module() ile çalıştırılır.

        Bu yaklaşım normal `import` statement'ından farklı olarak
        dosya yolundan doğrudan yükleme yapabilir — sys.path'e
        bağımlı değil.

        Parametreler:
            filename (str): Plugin dosya adı (örn: "weather_plugin.py")

        Dönüş:
            bool: Başarılı mı
        """
        filepath = os.path.join(PLUGIN_DIR, filename)
        module_name = f"plugin_{filename[:-3]}"  # .py uzantısını kaldır

        try:
            # Modül spec'i oluştur — dosya yolundan
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None:
                logger.error("Plugin spec oluşturulamadı → %s", filename)
                self.errors[filename] = "Spec oluşturulamadı"
                return False

            # Modül objesi oluştur
            module = importlib.util.module_from_spec(spec)

            # sys.modules'a ekle — circular import sorunlarını önler
            sys.modules[module_name] = module

            # Modülü çalıştır — bu sırada @registry.register tetiklenir
            spec.loader.exec_module(module)

            # Metadata çek (opsiyonel)
            metadata = getattr(module, "PLUGIN_INFO", {})
            if not metadata:
                metadata = {"name": filename[:-3], "version": "unknown"}

            self.loaded_plugins[filename] = metadata
            logger.info(
                "Plugin yüklendi → %s (v%s)",
                metadata.get("name", filename),
                metadata.get("version", "?")
            )
            return True

        except Exception as e:
            logger.error("Plugin yükleme hatası [%s]: %s", filename, e)
            self.errors[filename] = str(e)
            return False

    def get_plugin_list(self):
        """Yüklü plugin'lerin listesini döndürür."""
        if not self.loaded_plugins:
            return "Yüklü plugin yok."

        lines = []
        for filename, meta in self.loaded_plugins.items():
            name = meta.get("name", filename)
            version = meta.get("version", "?")
            desc = meta.get("description", "")
            line = f"  [{filename}] {name} v{version}"
            if desc:
                line += f" — {desc}"
            lines.append(line)

        result = f"Yüklü plugin'ler ({len(self.loaded_plugins)}):\n" + "\n".join(lines)

        # Hatalı plugin'ler varsa ekle
        if self.errors:
            result += f"\n\nHatalı plugin'ler ({len(self.errors)}):"
            for fname, err in self.errors.items():
                result += f"\n  [{fname}] {err}"

        return result

    def reload_plugin(self, filename):
        """
        Belirli bir plugin'i yeniden yükler (hot-reload).

        Dikkat: Registry'deki eski tool tanımları kalmaya devam eder.
        Aynı isimle register edilirse üzerine yazılır.
        """
        if not filename.endswith(".py"):
            filename += ".py"

        filepath = os.path.join(PLUGIN_DIR, filename)
        if not os.path.exists(filepath):
            return f"Plugin bulunamadı: {filename}"

        # Eski modülü sys.modules'dan kaldır
        module_name = f"plugin_{filename[:-3]}"
        if module_name in sys.modules:
            del sys.modules[module_name]

        success = self._load_plugin(filename)
        if success:
            return f"Plugin yeniden yüklendi: {filename}"
        return f"Plugin yükleme başarısız: {filename}"