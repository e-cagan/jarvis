# tools/system/sysinfo.py
# Sistem bilgisi tool'u — CPU, RAM, disk kullanımı.
# Ayrı tool olması LLM'in doğru çağırmasını kolaylaştırır.

import os
import platform

from tools.registry import registry
from utils.logger import setup_logger

logger = setup_logger("sysinfo")


@registry.register(
    name="system_info",
    description="Sistemin detaylı bilgisini döndürür: CPU, RAM kullanımı, disk durumu, işletim sistemi bilgisi.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def system_info():
    """Sistem bilgilerini toplar ve formatlanmış metin döndürür."""
    import shutil
    import subprocess

    logger.info("Sistem bilgisi toplanıyor")

    info_parts = []

    # İşletim sistemi
    info_parts.append(f"İşletim Sistemi: {platform.system()} {platform.release()}")
    info_parts.append(f"Makine: {platform.node()}")
    info_parts.append(f"Mimari: {platform.machine()}")

    # CPU bilgisi
    try:
        cpu_count = os.cpu_count()
        # CPU yükü (1, 5, 15 dakikalık ortalama)
        load_avg = os.getloadavg()
        info_parts.append(f"CPU: {cpu_count} çekirdek, yük ortalaması: {load_avg[0]:.1f} / {load_avg[1]:.1f} / {load_avg[2]:.1f}")
    except Exception:
        info_parts.append(f"CPU: {os.cpu_count()} çekirdek")

    # RAM bilgisi — /proc/meminfo'dan oku (Linux)
    try:
        with open("/proc/meminfo", "r") as f:
            meminfo = f.read()
        mem_total = mem_available = 0
        for line in meminfo.splitlines():
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1]) / 1024 / 1024  # KB → GB
            elif line.startswith("MemAvailable:"):
                mem_available = int(line.split()[1]) / 1024 / 1024
        mem_used = mem_total - mem_available
        info_parts.append(f"RAM: {mem_used:.1f} GB kullanılıyor / {mem_total:.1f} GB toplam ({mem_available:.1f} GB boş)")
    except Exception:
        info_parts.append("RAM: bilgi alınamadı")

    # Disk bilgisi
    try:
        disk = shutil.disk_usage("/")
        disk_total = disk.total / (1024 ** 3)
        disk_used = disk.used / (1024 ** 3)
        disk_free = disk.free / (1024 ** 3)
        info_parts.append(f"Disk: {disk_used:.1f} GB kullanılıyor / {disk_total:.1f} GB toplam ({disk_free:.1f} GB boş)")
    except Exception:
        info_parts.append("Disk: bilgi alınamadı")

    # GPU bilgisi (nvidia-smi varsa)
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(", ")
            info_parts.append(f"GPU: {parts[0]}, VRAM: {parts[1]} MB / {parts[2]} MB, Sıcaklık: {parts[3]}°C")
    except Exception:
        pass

    result = "\n".join(info_parts)
    logger.info("Sistem bilgisi toplandı")
    return result