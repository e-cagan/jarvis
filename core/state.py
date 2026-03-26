# core/state.py
# Konuşma durumu yönetimi — session persistence ve context window kontrolü.
# Mesaj geçmişini dosyaya kaydeder, başlangıçta yükler.
# Context window dolduğunda eski mesajları kırpar.

import json
import os
from datetime import datetime

from utils.logger import setup_logger

logger = setup_logger("state")

# Jarvis veri dizini
DATA_DIR = os.path.expanduser("~/.jarvis")
CONVERSATIONS_DIR = os.path.join(DATA_DIR, "conversations")
MEMORY_FILE = os.path.join(DATA_DIR, "memory.json")


class ConversationState:
    """
    Konuşma geçmişi yönetimi.

    Sorumlulukları:
    - Mesaj listesini tutma ve dosyaya kaydetme
    - Başlangıçta son oturumu yükleme
    - Context window sınırını aşmamak için eski mesajları kırpma
    - System prompt'u her zaman koruma (ilk mesaj)
    """

    def __init__(self, max_messages=12):
        """
        Parametreler:
            max_messages (int): Maksimum mesaj sayısı (system prompt hariç).
                Qwen 7B'nin context window'u ~32K token.
                Ortalama mesaj ~200 token olsa, 40 mesaj ~8K token.
                System prompt + tool tanımları ~2K token.
                Güvenli bir sınır.
        """
        self.max_messages = max_messages
        self.messages = []
        self.session_file = None

        # Dizinleri oluştur
        os.makedirs(CONVERSATIONS_DIR, exist_ok=True)

        logger.info("ConversationState başlatıldı → max %d mesaj", max_messages)

    def initialize(self, system_prompt):
        """
        Yeni oturum başlat veya son oturumu yükle.

        Parametreler:
            system_prompt (dict): {"role": "system", "content": "..."} formatında
        """
        # Oturum dosya adı — tarih bazlı
        today = datetime.now().strftime("%Y-%m-%d")
        self.session_file = os.path.join(CONVERSATIONS_DIR, f"{today}.json")

        # Bugünkü oturum var mı?
        if os.path.exists(self.session_file):
            self._load_session(system_prompt)
        else:
            # Yeni oturum
            self.messages = [system_prompt]
            logger.info("Yeni oturum başlatıldı")

    def _load_session(self, system_prompt):
        """
        Mevcut oturum dosyasını yükler.
        System prompt'u her zaman güncel olanla değiştirir
        (config değişmiş olabilir).
        """
        try:
            with open(self.session_file, "r", encoding="utf-8") as f:
                saved = json.load(f)

            # İlk mesaj (system prompt) her zaman güncel olandan gelsin
            # Geri kalanı dosyadan yükle
            self.messages = [system_prompt]

            for msg in saved:
                if msg.get("role") != "system":
                    self.messages.append(msg)

            # Kırpma uygula
            self._trim()

            logger.info("Oturum yüklendi → %d mesaj (%s)", len(self.messages), self.session_file)

        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Oturum yüklenemedi: %s — yeni oturum başlatılıyor", e)
            self.messages = [system_prompt]

    def add_message(self, message):
        """
        Mesaj ekler ve otomatik olarak dosyaya kaydeder.

        Parametreler:
            message (dict): {"role": "...", "content": "..."} formatında
        """
        self.messages.append(message)
        self._trim()
        self._save()

    def get_messages(self):
        """Tüm mesaj listesini döndürür."""
        return self.messages

    def _trim(self):
        """
        Mesaj sayısı max_messages'ı aştığında en eski mesajları siler.
        System prompt (ilk mesaj) her zaman korunur.

        Strateji: İlk mesaj (system) + son N mesaj
        Ortadaki eski mesajlar silinir.
        """
        if len(self.messages) <= self.max_messages + 1:  # +1 system prompt için
            return

        system = self.messages[0]
        # Son max_messages kadar mesajı tut
        recent = self.messages[-(self.max_messages):]
        self.messages = [system] + recent

        logger.debug("Mesajlar kırpıldı → %d mesaj", len(self.messages))

    def _save(self):
        """Mesajları dosyaya kaydeder."""
        if not self.session_file:
            return

        try:
            with open(self.session_file, "w", encoding="utf-8") as f:
                json.dump(self.messages, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error("Oturum kaydedilemedi: %s", e)

    def reset(self):
        """
        Konuşma geçmişini sıfırlar.
        System prompt korunur, dosya güncellenir.
        """
        if self.messages:
            self.messages = [self.messages[0]]
        self._save()
        logger.info("Konuşma geçmişi sıfırlandı")


class LongTermMemory:
    """
    Uzun süreli hafıza — konuşmalardan çıkarılan önemli bilgiler.

    Kullanıcı hakkında öğrenilen bilgileri (isim, tercihler, alışkanlıklar)
    kalıcı olarak saklar. Her konuşmanın başında system prompt'a enjekte edilir.

    Dosya formatı: {"facts": ["Kullanıcının adı Çağan", "Ubuntu 22.04 kullanıyor", ...]}
    """

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.facts = self._load()
        logger.info("LongTermMemory yüklendi → %d bilgi", len(self.facts))

    def _load(self):
        """Hafıza dosyasını yükler."""
        if not os.path.exists(MEMORY_FILE):
            return []
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("facts", [])
        except (json.JSONDecodeError, IOError):
            return []

    def _save(self):
        """Hafızayı dosyaya kaydeder."""
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump({"facts": self.facts}, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error("Hafıza kaydedilemedi: %s", e)

    def add_fact(self, fact):
        """
        Yeni bir bilgi ekler.
        Mevcut bilgilerle benzerlik kontrolü yapar:
        - Çok benzer bilgi varsa → günceller (eski yerine yeni koyar)
        - Benzer bilgi yoksa → yeni ekler

        Benzerlik metriği: Jaccard similarity
        İki cümledeki ortak kelimelerin, toplam benzersiz kelime sayısına oranı.
        Eşik 0.5 = kelimelerin yarısından fazlası ortaksa "aynı konu" sayılır.
        """
        similarity_threshold = 0.5

        best_match_index = -1
        best_score = 0.0

        fact_words = self._tokenize(fact)

        for i, existing in enumerate(self.facts):
            existing_words = self._tokenize(existing)
            score = self._jaccard_similarity(fact_words, existing_words)

            if score > best_score:
                best_score = score
                best_match_index = i

        if best_score >= similarity_threshold and best_match_index >= 0:
            # Benzer bilgi bulundu — güncelle
            old_fact = self.facts[best_match_index]
            self.facts[best_match_index] = fact.strip()
            self._save()
            logger.info("Bilgi güncellendi → '%s' → '%s' (benzerlik: %.2f)", old_fact, fact, best_score)
            return "updated"
        else:
            # Yeni bilgi — ekle
            self.facts.append(fact.strip())
            self._save()
            logger.info("Yeni bilgi kaydedildi → %s", fact)
            return "added"

    def _tokenize(self, text):
        """
        Metni küçük harfli kelime setine çevirir.
        Noktalama temizlenir — sadece kelimeler kalır.
        Set kullanıyoruz çünkü Jaccard set operasyonlarıyla çalışır.
        """
        # Basit tokenization — boşlukla böl, noktalama temizle
        words = text.lower().split()
        # Noktalama karakterlerini kaldır
        cleaned = set()
        for w in words:
            w = w.strip(".,!?;:'\"()[]{}").strip()
            if w:
                cleaned.add(w)
        return cleaned

    def _jaccard_similarity(self, set_a, set_b):
        """
        İki kelime seti arasındaki Jaccard benzerliğini hesaplar.

        Jaccard = |A ∩ B| / |A ∪ B|

        Örnek:
            A = {"kullanıcının", "favori", "dili", "python"}
            B = {"kullanıcının", "favori", "dili", "rust"}
            Kesişim = {"kullanıcının", "favori", "dili"} → 3
            Birleşim = {"kullanıcının", "favori", "dili", "python", "rust"} → 5
            Jaccard = 3/5 = 0.6 → eşik 0.5'i aşıyor → güncelle

        Dönüş:
            float: 0.0 (hiç benzemez) — 1.0 (aynı)
        """
        if not set_a or not set_b:
            return 0.0

        intersection = set_a & set_b  # Kesişim
        union = set_a | set_b         # Birleşim

        return len(intersection) / len(union)

    def get_facts(self):
        """Tüm bilgileri döndürür."""
        return self.facts

    def get_context_string(self):
        """
        System prompt'a enjekte edilecek format.
        Boşsa boş string döner — prompt'u kirletmez.
        """
        if not self.facts:
            return ""

        facts_text = "\n".join(f"- {fact}" for fact in self.facts)
        return f"\n## Kullanıcı Hakkında Bilinen Bilgiler\n{facts_text}\n"

    def remove_fact(self, index):
        """Index'e göre bilgi siler."""
        if 0 <= index < len(self.facts):
            removed = self.facts.pop(index)
            self._save()
            logger.info("Bilgi silindi → %s", removed)
            return removed
        return None