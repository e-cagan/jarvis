# core/scheduler.py
# Zamanlı görev yönetimi.
# APScheduler ile arka planda çalışır.
# Görevler ~/.jarvis/schedules.json'da persist edilir.
# Görev tetiklendiğinde orchestrator'a komut gönderir.

import json
import os
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

from utils.logger import setup_logger

logger = setup_logger("scheduler")

DATA_DIR = os.path.expanduser("~/.jarvis")
SCHEDULES_FILE = os.path.join(DATA_DIR, "schedules.json")


class JarvisScheduler:
    """
    Zamanlı görev yöneticisi.

    Üç tür zamanlama destekler:
    - once: Tek seferlik ("5 dakika sonra hatırlat")
    - interval: Tekrarlayan aralık ("her 30 dakikada bir")
    - cron: Cron-style ("her gün saat 08:00'de")

    Görev tetiklendiğinde bir callback fonksiyonu çağrılır.
    Bu callback orchestrator.process() olacak — yani görev
    bir Jarvis komutu olarak çalışır.
    """

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)

        # APScheduler — arka planda çalışır, ana thread'i bloklamaz
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()

        # Callback — görev tetiklendiğinde çağrılacak fonksiyon
        # Orchestrator tarafından set edilecek
        self._task_callback = None

        # Persist edilen görev tanımları
        self.tasks = self._load_tasks()

        # Kayıtlı görevleri yeniden zamanla
        self._restore_tasks()

        logger.info("Scheduler başlatıldı → %d kayıtlı görev", len(self.tasks))

    def set_callback(self, callback):
        """
        Görev tetiklendiğinde çağrılacak fonksiyonu ayarlar.
        Orchestrator başlatıldıktan sonra çağrılır.

        Parametreler:
            callback: func(task_command: str) → str
        """
        self._task_callback = callback

    def _load_tasks(self):
        """Görev dosyasını yükler."""
        if not os.path.exists(SCHEDULES_FILE):
            return []
        try:
            with open(SCHEDULES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _save_tasks(self):
        """Görevleri dosyaya kaydeder."""
        try:
            with open(SCHEDULES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.tasks, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error("Görevler kaydedilemedi: %s", e)

    def _restore_tasks(self):
        """
        Persist edilen görevleri yeniden zamanlar.
        Jarvis yeniden başlatıldığında çağrılır.
        Geçmiş tek seferlik görevler atlanır.
        """
        restored = 0
        for task in self.tasks:
            if task.get("active", True):
                success = self._schedule_task(task)
                if success:
                    restored += 1

        if restored > 0:
            logger.info("%d görev yeniden zamanlandı", restored)

    def add_task(self, task_id, command, schedule_type, **kwargs):
        """
        Yeni zamanlı görev ekler.

        Parametreler:
            task_id (str): Benzersiz görev ID'si
            command (str): Çalıştırılacak Jarvis komutu
                          (örn: "hava durumunu söyle", "emaillerimi kontrol et")
            schedule_type (str): "once", "interval", "cron"
            **kwargs:
                once: minutes=5 (kaç dakika sonra)
                interval: minutes=30 veya hours=1
                cron: hour=8, minute=0 (her gün saat 8:00)

        Dönüş:
            str: Başarı/hata mesajı
        """
        task = {
            "id": task_id,
            "command": command,
            "type": schedule_type,
            "params": kwargs,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "active": True
        }

        # Zamanla
        success = self._schedule_task(task)
        if not success:
            return f"Hata: Görev zamanlanamadı."

        # Persist et
        # Aynı ID varsa güncelle
        existing_idx = None
        for i, t in enumerate(self.tasks):
            if t["id"] == task_id:
                existing_idx = i
                break

        if existing_idx is not None:
            self.tasks[existing_idx] = task
        else:
            self.tasks.append(task)

        self._save_tasks()
        logger.info("Görev eklendi → %s: '%s' (%s)", task_id, command, schedule_type)
        return f"Görev zamanlandı: '{command}'"

    def _schedule_task(self, task):
        """APScheduler'a görevi ekler."""
        try:
            task_id = task["id"]
            schedule_type = task["type"]
            params = task.get("params", {})

            # Mevcut aynı ID'li job varsa kaldır
            existing = self.scheduler.get_job(task_id)
            if existing:
                self.scheduler.remove_job(task_id)

            if schedule_type == "once":
                minutes = params.get("minutes", 5)
                run_time = datetime.now() + timedelta(minutes=minutes)
                # Geçmiş zaman kontrolü
                if run_time < datetime.now():
                    logger.debug("Geçmiş tek seferlik görev atlandı → %s", task_id)
                    return False
                self.scheduler.add_job(
                    self._execute_task,
                    trigger=DateTrigger(run_date=run_time),
                    args=[task],
                    id=task_id
                )

            elif schedule_type == "interval":
                self.scheduler.add_job(
                    self._execute_task,
                    trigger=IntervalTrigger(
                        minutes=params.get("minutes", 0),
                        hours=params.get("hours", 0)
                    ),
                    args=[task],
                    id=task_id
                )

            elif schedule_type == "cron":
                self.scheduler.add_job(
                    self._execute_task,
                    trigger=CronTrigger(
                        hour=params.get("hour", 8),
                        minute=params.get("minute", 0)
                    ),
                    args=[task],
                    id=task_id
                )

            else:
                logger.error("Bilinmeyen schedule tipi: %s", schedule_type)
                return False

            return True

        except Exception as e:
            logger.error("Zamanlama hatası: %s", e)
            return False

    def _execute_task(self, task):
        """
        Zamanı gelen görevi çalıştırır.
        Callback üzerinden orchestrator'a komut gönderir.
        """
        command = task.get("command", "")
        task_id = task.get("id", "?")

        logger.info("Zamanlı görev tetiklendi → [%s]: '%s'", task_id, command)

        if self._task_callback:
            try:
                result = self._task_callback(command)
                logger.info("Görev sonucu → %s", str(result)[:200])
            except Exception as e:
                logger.error("Görev çalıştırma hatası [%s]: %s", task_id, e)
        else:
            logger.warning("Task callback ayarlanmamış — görev çalıştırılamadı")

        # Tek seferlik görevleri deaktive et
        if task.get("type") == "once":
            for t in self.tasks:
                if t["id"] == task_id:
                    t["active"] = False
                    break
            self._save_tasks()

    def remove_task(self, task_id):
        """Görevi kaldırır."""
        # APScheduler'dan kaldır
        try:
            self.scheduler.remove_job(task_id)
        except Exception:
            pass

        # Listeden kaldır
        for i, t in enumerate(self.tasks):
            if t["id"] == task_id:
                removed = self.tasks.pop(i)
                self._save_tasks()
                logger.info("Görev kaldırıldı → %s", task_id)
                return f"Görev kaldırıldı: '{removed['command']}'"

        return f"'{task_id}' ID'li görev bulunamadı."

    def list_tasks(self):
        """Tüm aktif görevleri listeler."""
        active = [t for t in self.tasks if t.get("active", True)]
        if not active:
            return "Zamanlanmış görev yok."

        lines = []
        for t in active:
            schedule_desc = self._describe_schedule(t)
            lines.append(f"  [{t['id']}] '{t['command']}' — {schedule_desc}")

        return "Zamanlanmış görevler:\n" + "\n".join(lines)

    def _describe_schedule(self, task):
        """Görev zamanlamasını okunabilir formata çevirir."""
        stype = task.get("type", "")
        params = task.get("params", {})

        if stype == "once":
            return f"Tek seferlik ({params.get('minutes', '?')} dakika sonra)"
        elif stype == "interval":
            if params.get("hours"):
                return f"Her {params['hours']} saatte bir"
            return f"Her {params.get('minutes', '?')} dakikada bir"
        elif stype == "cron":
            return f"Her gün saat {params.get('hour', '?')}:{params.get('minute', 0):02d}"
        return stype

    def shutdown(self):
        """Scheduler'ı durdurur."""
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler durduruldu")