# JARVIS — Kişisel AI Asistan

Tamamen lokal çalışan, sesli etkileşimli, tool calling destekli, hafızalı bir AI Agent pipeline.

## İçindekiler

- [Genel Bakış](#genel-bakış)
- [Mimari](#mimari)
- [Pipeline Akışı](#pipeline-akışı)
- [Teknoloji Yığını](#teknoloji-yığını)
- [Kurulum](#kurulum)
- [Kullanım](#kullanım)
- [Proje Yapısı](#proje-yapısı)
- [Modüller (Detaylı)](#modüller-detaylı)
  - [Core — Orchestrator, Event Loop, State](#core)
  - [LLM — Ollama Client, Prompt Manager, Response Parser](#llm)
  - [STT — Whisper, Wake Word, Audio](#stt)
  - [TTS — Piper](#tts)
  - [Tools — 23 Tool Detayı](#tools)
  - [Utils — Logger, Audio, Config](#utils)
- [Konfigürasyon](#konfigürasyon)
- [Memory Sistemi](#memory-sistemi)
- [Güvenlik](#güvenlik)
- [Bilinen Limitasyonlar](#bilinen-limitasyonlar)
- [Gelecek Planları](#gelecek-planları)

---

## Genel Bakış

Jarvis, sıfırdan tasarlanmış modüler bir sesli AI asistan pipeline'ıdır. Hiçbir bulut servisine bağımlı değildir — LLM, Speech-to-Text, Text-to-Speech ve tüm tool'lar tamamen lokal olarak çalışır.

Temel yetenekler:
- **Sesli etkileşim:** Mikrofon → Wake Word → Whisper STT → LLM → Piper TTS → Hoparlör
- **23 Tool:** Dosya yönetimi, terminal, uygulama kontrolü, web arama, not sistemi, hafıza, medya kontrolü, sistem bilgisi
- **AI Agent:** LLM hangi tool'u çağıracağına kendisi karar verir, tool'u çalıştırır, sonucu özetler
- **Hafıza:** Konuşmalar arası bilgi hatırlama (Jaccard similarity ile akıllı güncelleme)
- **Wake Word:** "Hey Jarvis" ile uyandırma (OpenWakeWord)
- **İki Mod:** Text (terminal) ve Voice (mikrofon/hoparlör)

---

## Mimari

Jarvis bir "tek model" değil, birbirine bağlı modüllerin bir zinciridir. Her modül tek bir sorumluluk taşır (Single Responsibility), modüller arasında abstract interface'ler (Dependency Inversion) ile bağlantı kurulur. Bir modülü değiştirdiğinizde diğerleri etkilenmez.

### Tasarım Desenleri

- **Strategy Pattern:** LLM, STT, TTS modüllerinde abstract base class + somut implementasyon. Yarın Whisper yerine başka bir STT kullanmak isterseniz aynı interface'i implement eden yeni bir class yazmanız yeterli.
- **Decorator Pattern:** Tool'lar `@registry.register()` decorator'ı ile kaydedilir. Yeni tool eklemek = bir fonksiyon yazıp decorator koymak.
- **Singleton Pattern:** `ToolRegistry` modül seviyesinde tek instance olarak oluşturulur. Tüm dosyalar aynı registry'ye erişir.
- **Dependency Injection:** `PromptManager` tool registry'yi parametre olarak alır, kendi oluşturmaz.
- **Observer/Pub-Sub benzeri akış:** Orchestrator modülleri koordine eder, modüller birbirini bilmez.

---

## Pipeline Akışı

### Text Modu
```
Kullanıcı (terminal) → Orchestrator → LLM (Ollama/Qwen)
                                          ↓
                                    Tool gerekli mi?
                                    /            \
                                 Evet            Hayır
                                  ↓                ↓
                            Tool Çalıştır    Düz metin yanıt
                                  ↓                ↓
                            Sonuç → LLM      Kullanıcıya göster
                            (özetle)
                                  ↓
                            Kullanıcıya göster
```

### Voice Modu
```
Mikrofon → Wake Word ("Hey Jarvis") → VAD (konuşma algıla)
    → Whisper STT (ses→metin) → Orchestrator → LLM → Tool(lar) → Yanıt
    → TTS Temizleme (URL/markdown kaldır) → Piper TTS (metin→ses) → Hoparlör
    → Wake Word beklemeye geri dön
```

### Tool Call Döngüsü (Orchestrator İçi)
```
1. Kullanıcı mesajını messages listesine ekle
2. Messages + tool tanımları → LLM'e gönder
3. Yanıtı parse et (response_parser)
4. Eğer tool_call:
   a. Tool'u registry'den bul ve çalıştır
   b. Tool sonucunu messages'a ekle (role: "tool")
   c. LLM'e tekrar gönder (sonucu özetlesin)
   d. Adım 3'e dön (max 5 round)
5. Eğer düz metin: kullanıcıya döndür
```

---

## Teknoloji Yığını

| Bileşen | Teknoloji | Neden Bu? |
|---------|-----------|-----------|
| LLM | Qwen 2.5 7B/14B (Ollama) | Lokal, native tool calling desteği, Türkçe yetkinlik |
| STT | faster-whisper (medium) | Whisper'ın 4-8x hızlı versiyonu, GPU float16 desteği |
| TTS | Piper (tr_TR-dfki-medium) | Lokal, internetsiz, ONNX tabanlı, hızlı |
| Wake Word | OpenWakeWord (hey_jarvis) | Hafif, CPU'da çalışır, önceden eğitilmiş model |
| VAD | WebRTC VAD | Google'ın endüstri standardı, GMM tabanlı, milisaniyede sonuç |
| Audio | sounddevice + PortAudio | Gerçek zamanlı mikrofon stream, numpy uyumlu |
| HTTP | requests | Ollama REST API ile iletişim |
| Web Search | duckduckgo-search | API key gerektirmez, ücretsiz |
| Web Scraping | BeautifulSoup4 | HTML → temiz metin dönüşümü |
| Config | PyYAML | Human-readable, yorum desteği |
| UI | Rich | Renkli terminal çıktısı |

---

## Kurulum

### Gereksinimler
- Ubuntu 22.04+ (test edilmiş)
- Python 3.10+
- NVIDIA GPU (önerilir, CPU'da da çalışır)
- Mikrofon ve hoparlör (voice mod için)

### 1. Sistem Bağımlılıkları
```bash
# Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Audio
sudo apt install portaudio19-dev libsndfile1

# Medya kontrolü (opsiyonel)
sudo apt install playerctl
```

### 2. Model İndirme
```bash
# LLM modeli
ollama pull qwen2.5:7b
# veya daha iyi tool calling için:
ollama pull qwen2.5:14b

# Piper TTS Türkçe ses modeli
mkdir -p ~/jarvis/models/piper
cd ~/jarvis/models/piper
wget -O tr_TR-dfki-medium.onnx 'https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium/tr_TR-dfki-medium.onnx?download=true'
wget -O tr_TR-dfki-medium.onnx.json 'https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium/tr_TR-dfki-medium.onnx.json?download=true'
```

### 3. Python Ortamı
```bash
cd ~/jarvis
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. CUDA Konfigürasyonu (GPU kullanıcıları)
Ollama'nın CUDA kütüphanelerini PATH'e ekleyin:
```bash
echo 'export LD_LIBRARY_PATH=/usr/local/lib/ollama/cuda_v12:$LD_LIBRARY_PATH' >> ~/jarvis/venv/bin/activate
source venv/bin/activate
```

### Dependencies (requirements.txt)
```
pyyaml==6.0.2
requests==2.32.3
rich==13.9.4
duckduckgo-search==7.5.1
faster-whisper==1.1.1
sounddevice==0.5.1
numpy==1.26.4
webrtcvad==2.0.10
piper-tts==1.2.0
beautifulsoup4==4.12.3
paho-mqtt==2.1.0
openwakeword==0.6.1
```

---

## Kullanım

### Text Modu
```bash
python3 main.py --text
# veya interaktif mod seçimi:
python3 main.py
```

### Voice Modu
```bash
python3 main.py --voice
```

### Özel Komutlar
| Komut | İşlev |
|-------|-------|
| `q`, `çık`, `quit`, `exit` | Programdan çık |
| `sıfırla`, `reset`, `temizle` | Konuşma geçmişini sıfırla (hafıza korunur) |
| "Hey Jarvis" | Wake word ile uyandır (voice modda) |
| "Görüşürüz" | Sesli kapanış (voice modda) |

### Data Yönetimi
```bash
# Konuşma geçmişini sil
rm -rf ~/.jarvis/conversations/

# Uzun süreli hafızayı sil
rm ~/.jarvis/memory.json

# Her şeyi sıfırla
rm -rf ~/.jarvis/

# Hafızayı kontrol et
cat ~/.jarvis/memory.json

# Notları kontrol et
cat ~/jarvis_notes.json
```

---

## Proje Yapısı

```
jarvis/
├── main.py                         # Giriş noktası — mod seçimi (text/voice)
├── config.yaml                     # Tüm konfigürasyon (LLM, STT, TTS, logging)
├── requirements.txt                # Python bağımlılıkları
│
├── core/                           # Pipeline koordinasyonu
│   ├── orchestrator.py             # Ana beyin — LLM ↔ Tool ↔ Memory koordinasyonu
│   ├── event_loop.py               # Voice mod döngüsü (wake word → dinle → işle → seslendir)
│   └── state.py                    # ConversationState + LongTermMemory
│
├── llm/                            # LLM iletişimi
│   ├── base.py                     # LLMBase abstract interface
│   ├── ollama_client.py            # Ollama HTTP API client
│   ├── prompt_manager.py           # System prompt oluşturma + tool tanımları
│   └── response_parser.py          # LLM yanıt parsing (native + fallback)
│
├── stt/                            # Speech-to-Text
│   ├── base.py                     # STTBase abstract interface
│   ├── whisper_stt.py              # faster-whisper implementasyonu
│   └── wake_word.py                # OpenWakeWord "Hey Jarvis" algılama
│
├── tts/                            # Text-to-Speech
│   ├── base.py                     # TTSBase abstract interface
│   └── piper_tts.py                # Piper TTS + metin temizleme
│
├── tools/                          # Agent tool'ları (23 adet)
│   ├── registry.py                 # Decorator-based tool kayıt sistemi
│   ├── system/
│   │   ├── terminal.py             # Shell komutu çalıştırma
│   │   ├── file_ops.py             # Dosya CRUD (7 tool)
│   │   ├── app_launcher.py         # Uygulama aç/kapat/listele
│   │   ├── sysinfo.py              # CPU/RAM/disk/GPU bilgisi
│   │   ├── notes.py                # Not sistemi (CRUD + arama)
│   │   ├── media.py                # Medya kontrolü (playerctl)
│   │   └── memory.py               # Uzun süreli hafıza tool'ları
│   ├── web/
│   │   ├── search.py               # DuckDuckGo arama + web fetch
│   │   └── email_client.py         # (Planlanıyor)
│   └── iot/
│       └── mqtt_client.py          # (Planlanıyor)
│
├── utils/                          # Yardımcı modüller
│   ├── logger.py                   # Merkezi loglama (terminal + dosya)
│   ├── audio.py                    # Mikrofon stream + VAD
│   └── config.py                   # Merkezi config loader (cache'li)
│
├── models/                         # Model dosyaları
│   └── piper/
│       ├── tr_TR-dfki-medium.onnx       # Piper Türkçe ses modeli
│       └── tr_TR-dfki-medium.onnx.json  # Model konfigürasyonu
│
└── vision/                         # (Gelecek faz)
    ├── screen_reader.py
    └── camera.py
```

---

## Modüller (Detaylı)

### Core

#### `core/orchestrator.py` — Pipeline Beyni
Tüm modülleri koordine eden merkezi sınıf. Kullanıcıdan mesaj alır, LLM'e gönderir, tool call varsa çalıştırır, sonucu tekrar LLM'e özetletir. Memory sistemiyle entegredir — system prompt'a uzun süreli hafıza bilgilerini enjekte eder.

Önemli parametreler:
- `max_tool_rounds = 5`: Sonsuz tool call döngüsünü engeller
- Memory bilgileri her oturum başında system prompt'a eklenir

#### `core/event_loop.py` — Voice Döngüsü
Sesli etkileşim döngüsü: Wake Word → Dinle → Transkribe → İşle → Seslendir → Tekrarla. `VoiceEventLoop` sınıfı tüm ses bileşenlerini (STT, TTS, AudioRecorder, WakeWord) başlatır ve koordine eder.

#### `core/state.py` — Hafıza Yönetimi
İki katmanlı hafıza sistemi:

**ConversationState (Kısa süreli):** Mesaj geçmişini tutar, dosyaya kaydeder (`~/.jarvis/conversations/YYYY-MM-DD.json`), bir sonraki açılışta yükler. `max_messages` ile context window sınırını korur — eski mesajlar otomatik kırpılır, system prompt her zaman korunur.

**LongTermMemory (Uzun süreli):** Kullanıcı hakkında öğrenilen bilgileri (`~/.jarvis/memory.json`) kalıcı olarak saklar. Jaccard similarity ile akıllı güncelleme yapar — benzer bilgi varsa (eşik >= 0.5) üzerine yazar, yoksa yeni ekler. Bu bilgiler her konuşmanın başında system prompt'a enjekte edilir.

Jaccard Similarity nasıl çalışır:
```
A = {"kullanıcının", "favori", "rengi", "mavi"}
B = {"kullanıcının", "favori", "rengi", "kırmızı"}
Kesişim = 3, Birleşim = 5
Jaccard = 3/5 = 0.6 → eşik 0.5'i aşıyor → güncelle
```

---

### LLM

#### `llm/base.py` — Abstract Interface
`LLMBase` ABC sınıfı iki abstract metod tanımlar: `generate()` (düz metin yanıt) ve `generate_with_tools()` (tool calling destekli yanıt). Tüm LLM client'ları bu interface'i implement eder.

#### `llm/ollama_client.py` — Ollama HTTP Client
Ollama'nın REST API'sine (`localhost:11434/api/chat`) POST request atar. `stream: false` ile tüm yanıtı tek seferde alır. Tool calling yanıtlarında `tool_calls` alanını kontrol eder — varsa `{"type": "tool_call", ...}`, yoksa `{"type": "text", ...}` döndürür.

Config'den okunan parametreler: `base_url`, `model`, `temperature` (0.1 — tool calling için düşük tutulur), `max_tokens` (Ollama'da `num_predict`).

Hata yönetimi: `ConnectionError` (Ollama çalışmıyor), `Timeout` (120s — uzun inference için), `HTTPError` (API hataları).

#### `llm/prompt_manager.py` — System Prompt Oluşturma
Modelin kimliğini, davranış kurallarını ve tool tanımlarını içeren system prompt'u oluşturur. Registry'den tüm tool schema'larını çeker, prompt'a ekler. İki mod destekler:

- **Native:** Tool tanımları Ollama'nın `tools` parametresine ayrı gönderilir
- **Fallback:** Tool tanımları JSON olarak system prompt'a gömülür (native başarısız olursa)

System prompt kuralları: Türkçe yanıt, kısa cevaplar, URL/markdown verme, sesli asistan davranışı, tool kullanım kuralları.

#### `llm/response_parser.py` — Yanıt Ayrıştırma
LLM yanıtını `{"type": "text"|"tool_call", ...}` formatına normalize eder. İki girdi tipini handle eder:

- **Dict (native):** `ollama_client`'ın döndürdüğü structured response'u doğrular
- **String (fallback):** Düz metin içindeki JSON tool_call'u bulur

Fallback parsing stratejisi: (1) tüm metni JSON olarak parse etmeyi dene, (2) markdown code block içinden JSON çıkar, (3) regex ile `{...}` bloğu bul, (4) düz metin olarak döndür.

---

### STT

#### `stt/whisper_stt.py` — faster-whisper STT
CTranslate2 optimize Whisper modeli. GPU'da CUDA + float16 ile çok hızlı inference. `language="tr"` ile dil algılama adımı atlanır (hız kazancı). `vad_filter=True` ile sessiz kısımlar atlanır ve hallucination azaltılır. `beam_size=5` standart doğruluk/hız dengesi.

Model boyutları: `tiny` (küçük/hızlı) → `base` → `small` → `medium` (önerilen) → `large-v3` (en doğru/yavaş).

#### `stt/wake_word.py` — Wake Word Algılama
OpenWakeWord ile "Hey Jarvis" algılama. CPU'da çalışır, GPU gerektirmez. Her 80ms'lik audio chunk'ı modele verir, model olasılık skoru döner. Skor `threshold` (default 0.5) aştığında wake word algılanmış sayılır.

#### `utils/audio.py` — Mikrofon + VAD
`sounddevice.RawInputStream` ile 16kHz mono mikrofon stream'i açar. WebRTC VAD her 30ms'lik frame'de konuşma kontrolü yapar. Ring buffer (son 300ms) konuşmanın başını kaçırmamak için tutulur. Sessizlik eşiği (default 0.8s) aşılınca kayıt durur. Çıktı: float32 numpy array, [-1.0, 1.0] aralığında — Whisper'ın beklediği format.

---

### TTS

#### `tts/piper_tts.py` — Piper TTS
ONNX Runtime üzerinde çalışan VITS modeli. Akış: metin → espeak-ng (foneme çevir) → VITS (ses üret) → numpy array → sounddevice (hoparlör). Dosyaya yazmadan bellekten doğrudan çalar.

**Metin Temizleme (`_clean_for_speech`):** LLM yanıtı sesli okunmadan önce temizlenir — URL'ler kaldırılır, markdown formatlaması soyulur, numaralı liste başlıkları temizlenir, birden fazla boşluk teke düşürülür.

Tek konuşmacılı modellerde `speaker_id` gönderilmez (`num_speakers` kontrolü). `length_scale` ile konuşma hızı ayarlanır.

---

### Tools

23 tool, decorator-based registry sistemiyle kayıtlıdır. Yeni tool eklemek:

```python
from tools.registry import registry

@registry.register(
    name="tool_adi",
    description="Tool'un ne yaptığının açıklaması",
    parameters={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "Parametre açıklaması"}
        },
        "required": ["param1"]
    }
)
def tool_adi(param1):
    # İş mantığı
    return "Sonuç string'i"
```

Sonra `main.py`'ye import eklemek yeterli:
```python
from tools.yeni_modul import tool_adi
```

#### Tool Registry (`tools/registry.py`)
Merkezi kayıt sistemi. `register()` decorator factory'si tool'u `_tools` dict'ine kaydeder. `get_all_schemas()` LLM'e gönderilecek tool tanımlarını döndürür (function referansı olmadan). `execute()` tool'u adıyla çağırır, `**arguments` ile dict'i keyword arguments'a açar. Bilinmeyen tool veya çalışma hatası durumunda hata mesajı döndürür (exception fırlatmaz).

#### System Tools

| Tool | Dosya | Açıklama |
|------|-------|----------|
| `run_terminal` | `terminal.py` | Shell komutu çalıştırır. Blacklist güvenlik kontrolü, 30s timeout, 5000 karakter çıktı limiti |
| `read_file` | `file_ops.py` | Dosya okur. Home dizini güvenlik sınırı, 10000 karakter limit, binary dosya kontrolü |
| `write_file` | `file_ops.py` | Dosyaya yazar. Ara dizinleri otomatik oluşturur |
| `append_to_file` | `file_ops.py` | Dosyanın sonuna ekler |
| `list_directory` | `file_ops.py` | Dizin içeriğini boyut bilgisiyle listeler |
| `delete_file` | `file_ops.py` | Dosya veya boş dizin siler (güvenlik: dolu dizin silmez) |
| `move_file` | `file_ops.py` | Taşır veya yeniden adlandırır |
| `copy_file` | `file_ops.py` | Dosya/dizin kopyalar (dizin için copytree) |
| `open_app` | `app_launcher.py` | Uygulama başlatır. Alias haritası (tarayıcı→firefox), Popen non-blocking, start_new_session |
| `close_app` | `app_launcher.py` | Uygulamayı kapatır (pkill SIGTERM) |
| `list_running_apps` | `app_launcher.py` | Bilinen çalışan uygulamaları listeler |
| `system_info` | `sysinfo.py` | CPU, RAM (/proc/meminfo), disk (shutil.disk_usage), GPU (nvidia-smi) bilgisi |
| `add_note` | `notes.py` | Not ekler (~/jarvis_notes.json) |
| `list_notes` | `notes.py` | Tüm notları listeler |
| `delete_note` | `notes.py` | ID'ye göre not siler |
| `edit_note` | `notes.py` | Not içeriğini günceller |
| `search_notes` | `notes.py` | Notlarda anahtar kelime araması |
| `remember` | `memory.py` | Bilgiyi uzun süreli hafızaya kaydeder (Jaccard ile akıllı güncelleme) |
| `recall_memory` | `memory.py` | Hafızadaki tüm bilgileri listeler |
| `forget` | `memory.py` | Hafızadan bilgi siler |
| `media_control` | `media.py` | Medya oynatıcı kontrolü (playerctl): play, pause, next, previous, volume, status |

#### Web Tools

| Tool | Dosya | Açıklama |
|------|-------|----------|
| `web_search` | `search.py` | DuckDuckGo ile web araması, başlık+URL+snippet döndürür |
| `web_fetch` | `search.py` | URL'den sayfa içeriği çeker, BeautifulSoup ile HTML→temiz metin, 5000 karakter limit |

---

### Utils

#### `utils/logger.py` — Merkezi Loglama
`config.yaml`'dan log seviyesi ve dosya ayarlarını okur. `setup_logger("modül_adı")` ile her modüle özel logger oluşturur. Terminal (StreamHandler) + dosya (FileHandler) çıktısı. Format: `saat | modül | seviye | mesaj`. Handler birikimine karşı koruma (aynı logger'a tekrar handler eklenmez).

#### `utils/audio.py` — Mikrofon + VAD
Yukarıda STT bölümünde detaylandırılmıştır.

#### `utils/config.py` — Config Loader
`config.yaml`'ı bir kez okuyup modül seviyesinde cache'ler. `get_config()` tüm config'i, `get_section("llm")` belirli bir bölümü döndürür.

---

## Konfigürasyon

`config.yaml` dosyası tüm ayarları merkezi olarak yönetir:

```yaml
# --- LLM ---
llm:
  provider: "ollama"
  base_url: "http://localhost:11434"
  model: "qwen2.5:7b"          # veya qwen2.5:14b
  temperature: 0.1              # Düşük = deterministik (tool calling için)
  max_tokens: 2048

# --- STT ---
stt:
  provider: "faster_whisper"
  model_size: "medium"          # tiny|base|small|medium|large-v3
  language: "tr"                # Dil algılamayı atla → hız kazancı
  device: "cuda"                # cuda|cpu
  compute_type: "float16"       # float16 (GPU) | int8 (CPU)
  silence_threshold: 0.8        # Sessizlik eşiği (saniye)
  sample_rate: 16000            # Whisper'ın beklediği format

# --- TTS ---
tts:
  provider: "piper"
  model_path: "models/piper/tr_TR-dfki-medium.onnx"
  speaker_id: 0
  speech_rate: 1.0              # < 1.0 hızlı, > 1.0 yavaş

# --- Asistan ---
assistant:
  name: "Jarvis"
  language: "tr"
  debug: true

# --- Loglama ---
logging:
  level: "DEBUG"                # DEBUG|INFO|WARNING|ERROR
  file: "jarvis.log"
```

### Parametre Açıklamaları

- **temperature 0.1:** Tool calling'de modelin JSON formatına sadık kalmasını istiyoruz. Yüksek temperature = yaratıcı ama tutarsız çıktı.
- **silence_threshold 0.8:** 0.8 saniye sessizlik = konuşma bitti. Çok kısa: cümle arası duraklarda keser. Çok uzun: geç yanıt verir.
- **sample_rate 16000:** Whisper 16kHz mono audio bekler. Farklı değer kullanmayın.
- **compute_type float16:** GPU'da en hızlı inference tipi. CPU'da `int8` kullanın.

---

## Memory Sistemi

### Kısa Süreli (ConversationState)
- Mesaj geçmişini `~/.jarvis/conversations/YYYY-MM-DD.json` dosyasına kaydeder
- Yeniden başlatıldığında bugünkü oturumu yükler
- `max_messages=20` ile context window korunur (system prompt + 20 mesaj)
- Kırpma stratejisi: system prompt (ilk) + son N mesaj korunur, ortadakiler silinir

### Uzun Süreli (LongTermMemory)
- `~/.jarvis/memory.json` dosyasında kalıcı bilgiler saklanır
- "Hatırla" komutuyla `remember` tool'u çağrılır
- Jaccard similarity ile akıllı güncelleme (eşik: 0.5)
- System prompt'a her oturum başında enjekte edilir
- `forget` tool'u ile silinebilir

### Jaccard Similarity Neden?
- Sıfır dependency (embedding model gerektirmez)
- Mikrosaniyede sonuç (latency yok)
- Bizim use case'imiz (yapısal benzer cümleler) için yeterli doğruluk
- Büyük hafızada yetersiz kalırsa embedding + cosine'a upgrade edilebilir

---

## Güvenlik

### Dosya Sistemi
- `_validate_path()` ile tüm dosya operasyonları home dizini (`~`) ile sınırlıdır
- `os.path.realpath()` ile path traversal saldırıları (`../../etc/passwd`) engellenir
- Dolu dizinler silinemez (kasıtlı güvenlik kararı)

### Terminal
- Blacklist sistemi tehlikeli komutları engeller: `rm -rf /`, `mkfs`, `dd if=`, fork bomb, `shutdown`, `reboot`
- 30 saniye timeout ile sonsuz döngü koruması
- 5000 karakter çıktı limiti ile context window koruması

### LLM
- `max_tool_rounds = 5` ile sonsuz tool call döngüsü engellenir
- Tool hataları exception fırlatmaz, hata mesajı döndürür (pipeline kırılmaz)

---

## Bilinen Limitasyonlar

### 7B Model Sınırlamaları
- 23 tool tanımı 7B model için çok fazla token — tool seçim hatası yapabilir
- Bazen tool çağırmak yerine kullanıcıya talimat verir
- Context window dolduğunda Çince'ye kayabilir (Qwen bilingual eğitim)
- Multi-step tool calling zayıf (iki tool'u sırayla çağırması gereken görevlerde)
- Çözüm: `qwen2.5:14b` modele geçiş (VRAM yeterliyse)

### STT
- Whisper Türkçe'de yabancı isimleri yanlış transkribe edebilir ("Jarvis" → "Carbis", "Puan" → "Poğan")
- Çok kısa sesler (< 0.5s) boş transkripsiyon üretebilir

### TTS
- Piper Türkçe dfki modeli doğal ama mükemmel değil
- Uzun URL'ler ve teknik terimler garip seslendirilebilir (temizleme fonksiyonu çoğunu yakalar)

### Web Search
- DuckDuckGo snippet'leri kısa — somut bilgi (sıcaklık, fiyat) için `web_fetch` gerekebilir
- Rate limiting olabilir (kişisel kullanım için yeterli)

---

## Gelecek Planları

- [ ] **IoT Entegrasyonu:** MQTT ile akıllı ev cihaz kontrolü (Mosquitto broker + ESP32)
- [ ] **Email:** Gmail API / SMTP ile mail gönderme ve okuma
- [ ] **Vision:** Kamera ile nesne tanıma, ekran okuma (OpenCV + YOLO)
- [ ] **Tool Birleştirme:** Benzer tool'ları birleştirerek 7B modelin yükünü azaltma
- [ ] **Streaming Response:** Token token yanıt gösterme (UX iyileştirme)
- [ ] **Embedding Memory:** Jaccard'dan sentence-transformer + cosine similarity'ye upgrade
- [ ] **Multi-tool Calling:** Tek turda birden fazla tool çağırma desteği
- [ ] **Scheduler:** Zamanlı görevler ("Her sabah 8'de hava durumunu söyle")
- [ ] **Plugin Sistemi:** Harici tool'ları dinamik yükleme

---

## Lisans

Bu proje kişisel kullanım ve eğitim amaçlı geliştirilmiştir.

---

*Son güncelleme: Mart 2026*