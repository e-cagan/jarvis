# tools/consolidated/memory_manager.py
# Birleştirilmiş hafıza yönetim tool'u.

from core.state import LongTermMemory
from tools.registry import registry
from utils.logger import setup_logger

logger = setup_logger("memory_manager")

memory = LongTermMemory()


@registry.register(
    name="memory",
    description="Uzun süreli hafıza yönetimi. Desteklenen action'lar: "
                "remember (bilgi kaydet/güncelle), recall (tüm bilgileri listele), "
                "forget (bilgi sil, index numarası ile).",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Yapılacak işlem: remember, recall, forget"
            },
            "fact": {
                "type": "string",
                "description": "remember için: hatırlanacak bilgi"
            },
            "index": {
                "type": "integer",
                "description": "forget için: silinecek bilginin sıra numarası (1'den başlar)"
            }
        },
        "required": ["action"]
    }
)
def memory_tool(action, fact=None, index=None):
    """Tek fonksiyondan tüm hafıza operasyonları."""
    action = action.lower().strip()

    if action == "remember":
        if not fact:
            return "Hata: 'fact' parametresi gerekli."
        result = memory.add_fact(fact)
        if result == "updated":
            return f"Bilgi güncellendi: {fact}"
        return f"Hatırladım: {fact}"

    elif action == "recall":
        facts = memory.get_facts()
        if not facts:
            return "Henüz kayıtlı bilgi yok."
        return "Bildiklerim:\n" + "\n".join(f"  {i+1}. {f}" for i, f in enumerate(facts))

    elif action == "forget":
        if index is None:
            return "Hata: 'index' parametresi gerekli."
        removed = memory.remove_fact(index - 1)
        if removed:
            return f"Unutuldu: {removed}"
        return "Bu numarada bilgi bulunamadı."

    else:
        return f"Bilinmeyen action: {action}. Geçerli: remember, recall, forget"