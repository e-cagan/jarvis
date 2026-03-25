# tools/system/memory.py
# Uzun süreli hafıza yönetim tool'ları.
# Kullanıcı "bunu hatırla" veya "ne biliyorsun benim hakkımda" diyebilir.

from core.state import LongTermMemory
from tools.registry import registry
from utils.logger import setup_logger

logger = setup_logger("memory_tool")

# Global memory instance — orchestrator ile paylaşılacak
memory = LongTermMemory()


@registry.register(
    name="remember",
    description="Kullanıcı hakkında önemli bir bilgiyi kalıcı olarak hafızaya kaydeder. "
                "Kullanıcı 'bunu hatırla', 'adım şu', 'şunu unutma' gibi ifadeler kullandığında kullanılır.",
    parameters={
        "type": "object",
        "properties": {
            "fact": {
                "type": "string",
                "description": "Hatırlanacak bilgi (örn: 'Kullanıcının adı Çağan', 'Python tercih ediyor')"
            }
        },
        "required": ["fact"]
    }
)
def remember(fact):
    """Bilgiyi uzun süreli hafızaya kaydeder."""
    memory.add_fact(fact)
    return f"Hatırladım: {fact}"


@registry.register(
    name="recall_memory",
    description="Kullanıcı hakkında bilinen tüm bilgileri listeler. "
                "'Benim hakkımda ne biliyorsun?', 'hafızanı göster' gibi sorularda kullanılır.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def recall_memory():
    """Hafızadaki tüm bilgileri döndürür."""
    facts = memory.get_facts()
    if not facts:
        return "Henüz hakkınızda kaydedilmiş bir bilgi yok."

    lines = [f"- {fact}" for fact in facts]
    return "Hakkınızda bildiklerim:\n" + "\n".join(lines)


@registry.register(
    name="forget",
    description="Hafızadan belirli bir bilgiyi siler. "
                "'Şunu unut', 'bu bilgiyi sil' gibi isteklerde kullanılır.",
    parameters={
        "type": "object",
        "properties": {
            "fact_index": {
                "type": "integer",
                "description": "Silinecek bilginin sıra numarası (1'den başlar)"
            }
        },
        "required": ["fact_index"]
    }
)
def forget(fact_index):
    """Hafızadan bilgi siler (1-indexed)."""
    removed = memory.remove_fact(fact_index - 1)  # Kullanıcıya 1-indexed gösteriyoruz
    if removed:
        return f"Unutuldu: {removed}"
    return "Bu numarada bir bilgi bulunamadı."