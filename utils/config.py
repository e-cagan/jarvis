# utils/config.py
# Merkezi konfigürasyon yönetimi.
# Tüm modüller config'e buradan erişir — tek bir yerden okunur, cache'lenir.

import os
import yaml


# Config bir kez okunur ve bellekte tutulur (module-level cache)
_config_cache = None


def get_config():
    """
    config.yaml'ı okuyup dict olarak döndürür.
    İlk çağrıda dosyadan okur, sonraki çağrılarda cache'den döner.

    Dönüş:
        dict: Tüm konfigürasyon
    """
    global _config_cache

    if _config_cache is not None:
        return _config_cache

    # Proje kökünü bul — bu dosya utils/ altında
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config.yaml"
    )

    with open(config_path, "r") as f:
        _config_cache = yaml.safe_load(f)

    return _config_cache


def get_section(section_name):
    """
    Config'in belirli bir bölümünü döndürür.

    Parametreler:
        section_name (str): Bölüm adı (örn: "llm", "stt", "tts", "assistant")

    Dönüş:
        dict: İlgili bölüm, yoksa boş dict
    """
    return get_config().get(section_name, {})