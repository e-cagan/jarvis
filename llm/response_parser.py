# llm/response_parser.py
# LLM yanıtlarını parse eden modül.
# İki modu var:
#   1. Native: ollama_client'ın döndürdüğü structured dict'i doğrular
#   2. Fallback: Düz metin içindeki JSON tool_call'u bulup çıkarır
# Orchestrator bu modülü kullanarak LLM yanıtını yorumlar.

import json
import re

from utils.logger import setup_logger

logger = setup_logger("response_parser")


def parse_response(response):
    """
    LLM yanıtını parse edip standart formata dönüştürür.

    Bu fonksiyon iki farklı girdi tipini handle eder:

    1. Dict girdi (native tool calling'den geliyor):
       ollama_client.generate_with_tools() zaten {"type": "tool_call"|"text", ...}
       formatında döndürüyor. Burada sadece doğrulama yapıyoruz.

    2. String girdi (fallback modundan geliyor):
       Model düz metin döndürmüş. İçinde tool_call JSON'u var mı diye bakıyoruz.

    Parametreler:
        response: dict veya str — LLM'den gelen yanıt

    Dönüş:
        dict: Her zaman şu iki formattan biri:
            {"type": "text", "content": "..."}
            {"type": "tool_call", "name": "...", "arguments": {...}}
    """
    # Mod 1: Native tool calling yanıtı (dict olarak gelir)
    if isinstance(response, dict):
        return _parse_native(response)

    # Mod 2: Fallback yanıtı (string olarak gelir)
    if isinstance(response, str):
        return _parse_fallback(response)

    # Beklenmeyen tip
    logger.error("Beklenmeyen yanıt tipi: %s", type(response))
    return {"type": "text", "content": str(response)}


def _parse_native(response):
    """
    ollama_client'ın döndürdüğü structured dict'i doğrular.

    Beklenen formatlar:
        {"type": "text", "content": "..."}
        {"type": "tool_call", "name": "...", "arguments": {...}}

    Eksik alan varsa güvenli default'a düşer.
    """
    resp_type = response.get("type", "text")

    if resp_type == "tool_call":
        name = response.get("name", "")
        arguments = response.get("arguments", {})

        # Temel doğrulama — tool adı boş olmamalı
        if not name:
            logger.warning("Tool call'da isim boş, text olarak düşürülüyor")
            return {"type": "text", "content": response.get("content", "Yanıt anlaşılamadı.")}

        # arguments dict olmalı — bazen model string döndürebilir
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                logger.warning("Tool arguments string parse edilemedi: %s", arguments)
                arguments = {}

        logger.info("Native parse → tool_call: %s(%s)", name, arguments)
        return {"type": "tool_call", "name": name, "arguments": arguments}

    else:
        content = response.get("content", "")
        logger.debug("Native parse → text (%d karakter)", len(content))
        return {"type": "text", "content": content}


def _parse_fallback(text):
    """
    Düz metin içindeki tool_call JSON'unu bulup parse eder.

    Model şu formatta döndürmesi bekleniyor:
        {"tool_call": {"name": "...", "arguments": {...}}}

    Ama model bazen:
        - Önüne/arkasına metin ekler
        - Markdown code block içine sarar (```json ... ```)
        - JSON'u bozuk üretir

    Bu fonksiyon bu durumları handle eder.

    Strateji:
    1. Önce tüm metni JSON olarak parse etmeyi dene
    2. Başarısızsa markdown code block içinden JSON çıkar
    3. Başarısızsa regex ile {...} bloğu bul
    4. Hiçbiri çalışmazsa düz metin olarak döndür
    """
    stripped = text.strip()

    # Strateji 1: Tüm metin geçerli bir JSON mı?
    parsed = _try_parse_json(stripped)
    if parsed:
        return _extract_tool_call(parsed, text)

    # Strateji 2: Markdown code block içinde JSON var mı?
    # ```json\n{...}\n``` veya ```\n{...}\n``` formatı
    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", stripped, re.DOTALL)
    if code_block_match:
        parsed = _try_parse_json(code_block_match.group(1).strip())
        if parsed:
            return _extract_tool_call(parsed, text)

    # Strateji 3: Metin içinde {...} bloğu bul
    # En dıştaki süslü parantezleri eşleştir
    brace_match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if brace_match:
        parsed = _try_parse_json(brace_match.group(0))
        if parsed:
            return _extract_tool_call(parsed, text)

    # Hiçbiri çalışmadı — düz metin
    logger.debug("Fallback parse → düz metin (%d karakter)", len(text))
    return {"type": "text", "content": text}


def _try_parse_json(text):
    """
    String'i JSON olarak parse etmeyi dener.
    Başarılıysa dict/list döner, başarısızsa None döner.
    Exception fırlatmaz — güvenli deneme.
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _extract_tool_call(parsed, original_text):
    """
    Parse edilmiş JSON'dan tool_call bilgisini çıkarır.

    İki olası format:
        {"tool_call": {"name": "...", "arguments": {...}}}  ← fallback prompt formatı
        {"name": "...", "arguments": {...}}                  ← doğrudan format

    Hiçbiri eşleşmezse düz metin olarak döner.
    """
    # Format 1: {"tool_call": {...}}
    if isinstance(parsed, dict) and "tool_call" in parsed:
        tool_data = parsed["tool_call"]
        name = tool_data.get("name", "")
        arguments = tool_data.get("arguments", {})

        if name:
            logger.info("Fallback parse → tool_call: %s(%s)", name, arguments)
            return {"type": "tool_call", "name": name, "arguments": arguments}

    # Format 2: {"name": "...", "arguments": {...}}
    if isinstance(parsed, dict) and "name" in parsed and "arguments" in parsed:
        name = parsed["name"]
        arguments = parsed["arguments"]

        if name:
            logger.info("Fallback parse → tool_call (direct): %s(%s)", name, arguments)
            return {"type": "tool_call", "name": name, "arguments": arguments}

    # JSON bulundu ama tool_call formatında değil — düz metin
    logger.debug("JSON bulundu ama tool_call formatında değil")
    return {"type": "text", "content": original_text}