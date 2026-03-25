# tools/system/notes.py
# Hızlı not alma sistemi.
# Notlar ~/jarvis_notes.json dosyasında saklanır.
# Ekle, listele, sil operasyonları.

import json
import os
from datetime import datetime

from tools.registry import registry
from utils.logger import setup_logger

logger = setup_logger("notes")

NOTES_FILE = os.path.expanduser("~/jarvis_notes.json")


def _load_notes():
    """Not dosyasını okur, yoksa boş liste döner."""
    if not os.path.exists(NOTES_FILE):
        return []
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_notes(notes):
    """Not listesini dosyaya yazar."""
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)


@registry.register(
    name="add_note",
    description="Yeni bir not ekler. Hızlı hatırlatma, fikir veya yapılacaklar için kullanılır.",
    parameters={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Not içeriği"
            }
        },
        "required": ["content"]
    }
)
def add_note(content):
    """Yeni not ekler."""
    notes = _load_notes()
    note = {
        "id": len(notes) + 1,
        "content": content,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    notes.append(note)
    _save_notes(notes)
    logger.info("Not eklendi → #%d: %s", note["id"], content[:50])
    return f"Not eklendi (#{note['id']}): {content}"


@registry.register(
    name="list_notes",
    description="Kayıtlı tüm notları listeler.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def list_notes():
    """Tüm notları listeler."""
    notes = _load_notes()
    if not notes:
        return "Hiç not yok."

    lines = []
    for note in notes:
        lines.append(f"#{note['id']} ({note['created']}): {note['content']}")

    logger.info("Notlar listelendi → %d adet", len(notes))
    return "\n".join(lines)


@registry.register(
    name="delete_note",
    description="Belirtilen numaralı notu siler.",
    parameters={
        "type": "object",
        "properties": {
            "note_id": {
                "type": "integer",
                "description": "Silinecek notun numarası"
            }
        },
        "required": ["note_id"]
    }
)
def delete_note(note_id):
    """ID'ye göre not siler."""
    notes = _load_notes()

    # ID'ye göre bul
    found = None
    for i, note in enumerate(notes):
        if note["id"] == note_id:
            found = i
            break

    if found is None:
        return f"#{note_id} numaralı not bulunamadı."

    removed = notes.pop(found)
    _save_notes(notes)
    logger.info("Not silindi → #%d", note_id)
    return f"Not silindi: {removed['content']}"


@registry.register(
    name="edit_note",
    description="Mevcut bir notu günceller. Not numarası ve yeni içerik gerektirir.",
    parameters={
        "type": "object",
        "properties": {
            "note_id": {
                "type": "integer",
                "description": "Güncellenecek notun numarası"
            },
            "new_content": {
                "type": "string",
                "description": "Notun yeni içeriği"
            }
        },
        "required": ["note_id", "new_content"]
    }
)
def edit_note(note_id, new_content):
    """Mevcut bir notu günceller."""
    notes = _load_notes()

    for note in notes:
        if note["id"] == note_id:
            old_content = note["content"]
            note["content"] = new_content
            note["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            _save_notes(notes)
            logger.info("Not güncellendi → #%d: '%s' → '%s'", note_id, old_content[:30], new_content[:30])
            return f"Not #{note_id} güncellendi: {new_content}"

    return f"#{note_id} numaralı not bulunamadı."


@registry.register(
    name="search_notes",
    description="Notlar içinde arama yapar. Anahtar kelimeye göre eşleşen notları döndürür.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Aranacak kelime veya ifade"
            }
        },
        "required": ["query"]
    }
)
def search_notes(query):
    """Notlar içinde arama yapar."""
    notes = _load_notes()
    if not notes:
        return "Hiç not yok."

    query_lower = query.lower()
    matches = []
    for note in notes:
        if query_lower in note["content"].lower():
            matches.append(f"#{note['id']} ({note['created']}): {note['content']}")

    if not matches:
        return f"'{query}' ile eşleşen not bulunamadı."

    logger.info("Not araması → '%s', %d sonuç", query, len(matches))
    return f"'{query}' ile eşleşen {len(matches)} not:\n" + "\n".join(matches)