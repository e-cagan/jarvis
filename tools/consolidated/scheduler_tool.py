# tools/consolidated/scheduler_tool.py
# Zamanlı görev yönetim tool'u.

from datetime import datetime

from tools.registry import registry
from utils.logger import setup_logger

logger = setup_logger("scheduler_tool")

# Global scheduler instance — orchestrator tarafından set edilecek
_scheduler = None


def set_scheduler(scheduler):
    """Orchestrator tarafından çağrılır."""
    global _scheduler
    _scheduler = scheduler


@registry.register(
    name="scheduler",
    description="Zamanlı görev yönetimi. Desteklenen action'lar: "
                "add_once (X dakika sonra çalıştır), "
                "add_daily (her gün belirli saatte çalıştır), "
                "add_interval (belirli aralıklarla tekrarla), "
                "list (görevleri listele), remove (görev kaldır).",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "İşlem: add_once, add_daily, add_interval, list, remove"
            },
            "command": {
                "type": "string",
                "description": "Çalıştırılacak Jarvis komutu (örn: 'hava durumunu söyle')"
            },
            "minutes": {
                "type": "integer",
                "description": "add_once: kaç dakika sonra. add_interval: kaç dakikada bir"
            },
            "hour": {
                "type": "integer",
                "description": "add_daily: saat (0-23)"
            },
            "minute": {
                "type": "integer",
                "description": "add_daily: dakika (0-59, varsayılan 0)"
            },
            "task_id": {
                "type": "string",
                "description": "remove: kaldırılacak görev ID'si"
            }
        },
        "required": ["action"]
    }
)
def scheduler(action, command=None, minutes=None, hour=None, minute=0, task_id=None):
    """Zamanlı görev yönetimi."""
    if _scheduler is None:
        return "Hata: Scheduler başlatılmamış."

    action = action.lower().strip()

    if action == "add_once":
        if not command or not minutes:
            return "Hata: 'command' ve 'minutes' gerekli."
        tid = f"once_{datetime.now().strftime('%H%M%S')}"
        return _scheduler.add_task(tid, command, "once", minutes=minutes)

    elif action == "add_daily":
        if not command or hour is None:
            return "Hata: 'command' ve 'hour' gerekli."
        tid = f"daily_{hour:02d}{minute:02d}"
        return _scheduler.add_task(tid, command, "cron", hour=hour, minute=minute)

    elif action == "add_interval":
        if not command or not minutes:
            return "Hata: 'command' ve 'minutes' gerekli."
        tid = f"interval_{minutes}m"
        return _scheduler.add_task(tid, command, "interval", minutes=minutes)

    elif action == "list":
        return _scheduler.list_tasks()

    elif action == "remove":
        if not task_id:
            return "Hata: 'task_id' gerekli. Önce 'list' ile görevleri görün."
        return _scheduler.remove_task(task_id)

    else:
        return f"Bilinmeyen action: {action}. Geçerli: add_once, add_daily, add_interval, list, remove"