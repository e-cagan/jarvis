# utils/logger.py
# Merkezi loglama altyapısı.
# Diğer tüm modüller bu dosyadan logger alır.
# Config'den log seviyesi ve dosya ayarlarını okur.

import logging
import os
import yaml


def _load_config():
    """
    config.yaml dosyasını okuyup dict olarak döndürür.
    Logger projenin ilk kurulan parçası olduğu için
    config okumayı kendi içinde yapıyor — başka modüle bağımlı değil.
    """
    # Bu dosya utils/ klasöründe, config.yaml bir üst dizinde
    # __file__ → bu dosyanın mutlak yolu
    # dirname ile iki kez yukarı çıkıyoruz: utils/ → jarvis/
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config.yaml"
    )

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def setup_logger(name):
    """
    Verilen modül adıyla yapılandırılmış bir logger döndürür.

    Parametreler:
        name (str): Logger'ı oluşturan modülün adı.
                     Örn: "ollama_client", "orchestrator"

    Dönüş:
        logging.Logger: Yapılandırılmış logger objesi.

    Kullanım:
        from utils.logger import setup_logger
        logger = setup_logger("ollama_client")
        logger.info("Ollama'ya bağlanılıyor...")
        logger.debug("Raw response: %s", response)
        logger.error("Bağlantı başarısız: %s", err)
    """
    config = _load_config()
    log_config = config.get("logging", {})

    # Config'deki string seviyeyi ("DEBUG") logging sabitine çevir (10)
    # Geçersiz bir değer gelirse INFO'ya düş
    level_str = log_config.get("level", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)

    # Logger objesini oluştur
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Aynı logger'a tekrar handler eklenmesini engelle
    # (Modül birden fazla kez import edilirse handler'lar birikir)
    if logger.handlers:
        return logger

    # Log formatı: zaman | modül | seviye | mesaj
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S"
    )

    # Terminal handler — her zaman aktif
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # Dosya handler — config'de file belirtilmişse
    log_file = log_config.get("file")
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger