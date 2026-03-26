# tools/consolidated/notes_manager.py
# Birleştirilmiş not yönetim tool'u.

import json
import os
from datetime import datetime

from tools.registry import registry
from utils.logger import setup_logger

logger = setup_logger("notes_manager")

NOTES_FILE = os.path.expanduser("~/jarvis_notes.json")


def _load_notes():
    if not os.path.exists(NOTES_FILE):
        return []
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_notes(notes):
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)


@registry.register(
    name="notes",
    description="Not yönetimi. Desteklenen action'lar: "
                "add (not ekle), list (notları listele), delete (not sil), "
                "edit (not düzenle), search (notlarda ara).",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Yapılacak işlem: add, list, delete, edit, search"
            },
            "content": {
                "type": "string",
                "description": "add ve edit için: not içeriği. search için: arama kelimesi"
            },
            "note_id": {
                "type": "integer",
                "description": "delete ve edit için: not numarası"
            }
        },
        "required": ["action"]
    }
)
def notes(action, content=None, note_id=None):
    """Tek fonksiyondan tüm not operasyonları."""
    action = action.lower().strip()

    if action == "add":
        if not content:
            return "Hata: 'content' parametresi gerekli."
        notes_list = _load_notes()
        note = {"id": len(notes_list) + 1, "content": content, "created": datetime.now().strftime("%Y-%m-%d %H:%M")}
        notes_list.append(note)
        _save_notes(notes_list)
        logger.info("Not eklendi → #%d", note["id"])
        return f"Not eklendi (#{note['id']}): {content}"

    elif action == "list":
        notes_list = _load_notes()
        if not notes_list:
            return "Hiç not yok."
        return "\n".join(f"#{n['id']} ({n['created']}): {n['content']}" for n in notes_list)

    elif action == "delete":
        if note_id is None:
            return "Hata: 'note_id' parametresi gerekli."
        notes_list = _load_notes()
        for i, n in enumerate(notes_list):
            if n["id"] == note_id:
                removed = notes_list.pop(i)
                _save_notes(notes_list)
                return f"Not silindi: {removed['content']}"
        return f"#{note_id} numaralı not bulunamadı."

    elif action == "edit":
        if note_id is None or not content:
            return "Hata: 'note_id' ve 'content' parametreleri gerekli."
        notes_list = _load_notes()
        for n in notes_list:
            if n["id"] == note_id:
                n["content"] = content
                n["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                _save_notes(notes_list)
                return f"Not #{note_id} güncellendi: {content}"
        return f"#{note_id} numaralı not bulunamadı."

    elif action == "search":
        if not content:
            return "Hata: 'content' parametresine arama kelimesi girin."
        notes_list = _load_notes()
        matches = [f"#{n['id']} ({n['created']}): {n['content']}" for n in notes_list if content.lower() in n["content"].lower()]
        if not matches:
            return f"'{content}' ile eşleşen not bulunamadı."
        return "\n".join(matches)

    else:
        return f"Bilinmeyen action: {action}. Geçerli: add, list, delete, edit, search"