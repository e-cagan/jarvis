# tools/consolidated/email_tool.py
# Gmail CRUD tool'u — gönder, oku, ara, sil.
# SMTP ile gönderim, IMAP ile okuma/arama/silme.
# App Password ile kimlik doğrulama (OAuth2 gerektirmez).

import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from datetime import datetime

from tools.registry import registry
from utils.config import get_section
from utils.logger import setup_logger

logger = setup_logger("email_tool")


def _get_email_config():
    """Email konfigürasyonunu yükler."""
    config = get_section("email")
    if not config.get("address") or not config.get("app_password"):
        return None
    return config


def _decode_header_value(value):
    """
    Email başlıklarını decode eder.
    Email başlıkları bazen base64 veya quoted-printable ile encode edilir.
    decode_header() bu encoding'leri çözer.
    """
    if value is None:
        return ""
    decoded_parts = decode_header(value)
    result = ""
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result += part.decode(charset or "utf-8", errors="replace")
        else:
            result += part
    return result


def _connect_imap():
    """
    IMAP bağlantısı kurar ve giriş yapar.
    IMAP (Internet Message Access Protocol) email okumak için kullanılır.
    SSL ile şifreli bağlantı kurar (port 993).
    """
    config = _get_email_config()
    if not config:
        return None, "Hata: Email konfigürasyonu eksik. config.yaml'ı kontrol edin."

    try:
        # IMAP4_SSL → SSL ile şifreli bağlantı
        imap = imaplib.IMAP4_SSL(config["imap_server"], config.get("imap_port", 993))
        # App Password ile giriş
        imap.login(config["address"], config["app_password"].replace(" ", ""))
        return imap, None
    except imaplib.IMAP4.error as e:
        logger.error("IMAP giriş hatası: %s", e)
        return None, f"Hata: Email girişi başarısız — {e}"
    except Exception as e:
        logger.error("IMAP bağlantı hatası: %s", e)
        return None, f"Hata: Email sunucusuna bağlanılamadı — {e}"


def _parse_email_message(msg):
    """
    Ham email mesajını okunabilir formata çevirir.
    Email'ler MIME formatındadır — multipart olabilir (text + html + ekler).
    Biz sadece text/plain kısmını alıyoruz.
    """
    subject = _decode_header_value(msg.get("Subject", ""))
    sender = _decode_header_value(msg.get("From", ""))
    date = msg.get("Date", "")

    # Body çıkarma — multipart ise text/plain kısmını al
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                try:
                    body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    body = "(içerik okunamadı)"
                break
    else:
        try:
            body = msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            body = "(içerik okunamadı)"

    # Body'yi kırp
    if len(body) > 2000:
        body = body[:2000] + "\n... (kırpıldı)"

    return {
        "subject": subject,
        "from": sender,
        "date": date,
        "body": body.strip()
    }


@registry.register(
    name="email",
    description="Email yönetimi (Gmail). Desteklenen action'lar: "
                "send (mail gönder), inbox (gelen kutusunu oku), "
                "search (mail ara), delete (mail sil).",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Yapılacak işlem: send, inbox, search, delete"
            },
            "to": {
                "type": "string",
                "description": "send için: alıcı email adresi"
            },
            "subject": {
                "type": "string",
                "description": "send için: email konusu"
            },
            "body": {
                "type": "string",
                "description": "send için: email içeriği"
            },
            "query": {
                "type": "string",
                "description": "search için: arama sorgusu (konu veya gönderen)"
            },
            "count": {
                "type": "integer",
                "description": "inbox için: okunacak mail sayısı (varsayılan 5)"
            },
            "email_id": {
                "type": "string",
                "description": "delete için: silinecek mailin ID'si"
            }
        },
        "required": ["action"]
    }
)
def email_tool(action, to=None, subject=None, body=None, query=None, count=5, email_id=None):
    """Tek fonksiyondan tüm email operasyonları."""
    action = action.lower().strip()

    if action == "send":
        return _send_email(to, subject, body)
    elif action == "inbox":
        return _read_inbox(count)
    elif action == "search":
        return _search_email(query, count)
    elif action == "delete":
        return _delete_email(email_id)
    else:
        return f"Bilinmeyen action: {action}. Geçerli: send, inbox, search, delete"


def _send_email(to, subject, body):
    """
    SMTP ile email gönderir.
    SMTP (Simple Mail Transfer Protocol) email göndermek için kullanılır.
    Gmail SMTP TLS ile çalışır (port 587).
    """
    if not to:
        return "Hata: 'to' (alıcı) parametresi gerekli."
    if not subject:
        subject = "(Konusuz)"
    if not body:
        return "Hata: 'body' (içerik) parametresi gerekli."

    config = _get_email_config()
    if not config:
        return "Hata: Email konfigürasyonu eksik."

    try:
        # MIME mesajı oluştur
        msg = MIMEMultipart()
        msg["From"] = config["address"]
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # SMTP bağlantısı
        # starttls() → düz bağlantıyı TLS ile şifreler
        with smtplib.SMTP(config["smtp_server"], config.get("smtp_port", 587)) as server:
            server.starttls()
            server.login(config["address"], config["app_password"].replace(" ", ""))
            server.send_message(msg)

        logger.info("Email gönderildi → %s (%s)", to, subject)
        return f"Email gönderildi: '{subject}' → {to}"

    except smtplib.SMTPAuthenticationError:
        return "Hata: Email girişi başarısız. App Password'ü kontrol edin."
    except Exception as e:
        logger.error("Email gönderme hatası: %s", e)
        return f"Hata: {e}"


def _read_inbox(count=5):
    """
    IMAP ile gelen kutusundaki son N emaili okur.
    INBOX klasörünü seçer, son mesajlardan geriye doğru okur.
    """
    imap, error = _connect_imap()
    if error:
        return error

    try:
        # INBOX klasörünü seç (readonly — değişiklik yapma)
        imap.select("INBOX", readonly=True)

        # Tüm mesaj ID'lerini al
        status, messages = imap.search(None, "ALL")
        if status != "OK":
            return "Hata: Gelen kutusu okunamadı."

        msg_ids = messages[0].split()
        if not msg_ids:
            return "Gelen kutunuz boş."

        # Son N mesajı al (en yeniden en eskiye)
        recent_ids = msg_ids[-count:]
        recent_ids.reverse()

        results = []
        for msg_id in recent_ids:
            status, data = imap.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue

            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            parsed = _parse_email_message(msg)

            results.append(
                f"ID: {msg_id.decode()}\n"
                f"Kimden: {parsed['from']}\n"
                f"Konu: {parsed['subject']}\n"
                f"Tarih: {parsed['date']}\n"
                f"İçerik: {parsed['body'][:200]}"
            )

        imap.logout()

        if not results:
            return "Gelen kutusunda mail bulunamadı."

        return f"Son {len(results)} email:\n\n" + "\n\n---\n\n".join(results)

    except Exception as e:
        logger.error("Inbox okuma hatası: %s", e)
        try:
            imap.logout()
        except Exception:
            pass
        return f"Hata: {e}"


def _search_email(query, count=5):
    """
    IMAP SEARCH komutuyla email arar.
    Konu veya gönderene göre arama yapar.
    IMAP search syntax: OR (FROM "x") (SUBJECT "x")
    """
    if not query:
        return "Hata: 'query' parametresi gerekli."

    imap, error = _connect_imap()
    if error:
        return error

    try:
        imap.select("INBOX", readonly=True)

        # Hem konu hem gönderende ara
        # IMAP search UTF-8 destekler ama bazı sunucular sorun çıkarabilir
        search_criteria = f'(OR (FROM "{query}") (SUBJECT "{query}"))'

        status, messages = imap.search(None, search_criteria)
        if status != "OK":
            return f"Arama başarısız: {query}"

        msg_ids = messages[0].split()
        if not msg_ids:
            imap.logout()
            return f"'{query}' ile eşleşen mail bulunamadı."

        # Son N sonucu al
        recent_ids = msg_ids[-count:]
        recent_ids.reverse()

        results = []
        for msg_id in recent_ids:
            status, data = imap.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue

            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            parsed = _parse_email_message(msg)

            results.append(
                f"ID: {msg_id.decode()}\n"
                f"Kimden: {parsed['from']}\n"
                f"Konu: {parsed['subject']}\n"
                f"Tarih: {parsed['date']}"
            )

        imap.logout()

        return f"'{query}' araması — {len(results)} sonuç:\n\n" + "\n\n".join(results)

    except Exception as e:
        logger.error("Email arama hatası: %s", e)
        try:
            imap.logout()
        except Exception:
            pass
        return f"Hata: {e}"


def _delete_email(email_id):
    """
    IMAP ile emaili siler (çöp kutusuna taşır).
    Gmail'de silme = \\Deleted flag + expunge.
    """
    if not email_id:
        return "Hata: 'email_id' parametresi gerekli. Önce inbox veya search ile ID'yi öğrenin."

    imap, error = _connect_imap()
    if error:
        return error

    try:
        imap.select("INBOX")

        # Mesajı Deleted olarak işaretle
        status, _ = imap.store(email_id.encode(), "+FLAGS", "\\Deleted")
        if status != "OK":
            imap.logout()
            return f"Hata: ID {email_id} bulunamadı veya silinemedi."

        # Silinen mesajları kalıcı kaldır
        imap.expunge()
        imap.logout()

        logger.info("Email silindi → ID: %s", email_id)
        return f"Email (ID: {email_id}) silindi."

    except Exception as e:
        logger.error("Email silme hatası: %s", e)
        try:
            imap.logout()
        except Exception:
            pass
        return f"Hata: {e}"