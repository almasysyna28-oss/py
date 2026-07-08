"""
ربات بله: دانلود از یوتیوب با انتخاب کیفیت
----------------------------------------------
پیش‌نیازها:
    pip install yt-dlp requests

نحوه کار:
    1. کاربر لینک یوتیوب می‌فرسته
    2. ربات فرمت‌های موجود (progressive - بدون نیاز به ffmpeg) رو با حجمشون
       به‌صورت دکمه نشون می‌ده
    3. کاربر کیفیت مورد نظر رو انتخاب می‌کنه
    4. ربات همون کیفیت رو دانلود و ارسال می‌کنه

نکته: از فرمت‌های progressive (صدا+ویدیو در یک فایل) استفاده می‌کنیم
تا نیازی به نصب ffmpeg روی سرور نباشه.
"""

import os
import re
import time
import requests
import yt_dlp

# ============ تنظیمات ============
BALE_TOKEN = "1624551307:sXvFHJ0-5wGM-VwHbGqW7DuLH0DUHNKZfP8"
BALE_BASE_URL = f"https://tapi.bale.ai/bot{BALE_TOKEN}"

DOWNLOAD_DIR = "downloads"
MAX_SIZE_MB = 45
POLL_INTERVAL_SECONDS = 2

YOUTUBE_URL_PATTERN = re.compile(
    r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w\-]+[^\s]*"
)

COOKIES_FILE = "cookies.txt"  # اگه این فایل کنار کد موجود باشه، خودکار استفاده میشه


def _base_ydl_opts() -> dict:
    opts = {}
    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    return opts


# حافظه موقت: chat_id -> {"url": ..., "formats": {format_id: label}}
pending_requests: dict[int, dict] = {}


def send_message(chat_id: int, text: str, reply_markup: dict | None = None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{BALE_BASE_URL}/sendMessage", json=payload)


def answer_callback(callback_id: str):
    try:
        requests.post(f"{BALE_BASE_URL}/answerCallbackQuery", json={"callback_query_id": callback_id})
    except Exception:
        pass


def format_size(num_bytes) -> str:
    if not num_bytes:
        return "نامشخص"
    mb = num_bytes / (1024 * 1024)
    return f"{mb:.1f} MB"


def get_available_qualities(url: str):
    """
    فرمت‌های progressive (صدا+ویدیو ترکیب‌شده، بدون نیاز به ffmpeg) رو
    استخراج می‌کنه و به ازای هر رزولوشن، بهترین گزینه رو نگه می‌داره.
    خروجی: لیستی از (format_id, height, filesize)
    """
    ydl_opts = {"quiet": True, "noplaylist": True, **_base_ydl_opts()}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    best_by_height = {}
    for f in info.get("formats", []):
        if f.get("vcodec") == "none" or f.get("acodec") == "none":
            continue  # فقط فرمت‌های progressive (هم صدا هم ویدیو)
        if f.get("ext") != "mp4":
            continue
        height = f.get("height")
        if not height:
            continue
        size = f.get("filesize") or f.get("filesize_approx") or 0
        if height not in best_by_height or size > best_by_height[height][1]:
            best_by_height[height] = (f["format_id"], size)

    result = [(fid, h, size) for h, (fid, size) in best_by_height.items()]
    result.sort(key=lambda x: x[1], reverse=True)  # بزرگ‌ترین کیفیت اول
    return result, info.get("title", "video")


def download_format(url: str, format_id: str) -> tuple[str | None, str]:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    ydl_opts = {
        "format": format_id,
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s_%(format_id)s.%(ext)s"),
        "noplaylist": True,
        **_base_ydl_opts(),
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
            return filepath, ""
    except Exception as e:
        print(f"❌ خطا در دانلود: {e}")
        return None, str(e)


def send_video(chat_id: int, filepath: str, caption: str = "") -> bool:
    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        send_message(chat_id, f"⚠️ حجم فایل {size_mb:.1f} مگابایت شد و بیشتر از سقف مجازه. لطفاً کیفیت پایین‌تری انتخاب کنید.")
        return False
    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                f"{BALE_BASE_URL}/sendVideo",
                data={"chat_id": chat_id, "caption": caption},
                files={"video": f},
                timeout=300,
            )
        return bool(resp.json().get("ok"))
    except Exception as e:
        print(f"❌ خطا در ارسال فایل: {e}")
        return False


def handle_message(chat_id: int, text: str):
    if not text:
        return

    if text.strip() in ("/start", "start"):
        send_message(chat_id, "سلام! 👋 لینک ویدیوی یوتیوب رو برام بفرست تا کیفیت‌های موجود رو نشونت بدم.")
        return

    match = YOUTUBE_URL_PATTERN.search(text)
    if not match:
        send_message(chat_id, "لینک یوتیوب معتبری پیدا نکردم 🤔 لطفاً یک لینک درست بفرست.")
        return

    url = match.group(0)
    send_message(chat_id, "🔎 در حال بررسی کیفیت‌های موجود...")

    try:
        qualities, title = get_available_qualities(url)
    except Exception as e:
        send_message(chat_id, f"❌ نتونستم اطلاعات ویدیو رو بگیرم.\n\nخطا:\n{str(e)[:300]}")
        return

    if not qualities:
        send_message(chat_id, "❌ هیچ کیفیت قابل‌دانلودی (بدون نیاز به پردازش اضافه) برای این ویدیو پیدا نشد.")
        return

    # ذخیره برای استفاده بعد از انتخاب کاربر
    format_map = {}
    buttons = []
    for format_id, height, size in qualities:
        label = f"{height}p - {format_size(size)}"
        format_map[format_id] = label
        buttons.append([{"text": label, "callback_data": f"dl:{format_id}"}])

    pending_requests[chat_id] = {"url": url, "formats": format_map}

    send_message(
        chat_id,
        f"🎬 {title}\n\nکیفیت مورد نظر رو انتخاب کن:",
        reply_markup={"inline_keyboard": buttons},
    )


def handle_callback(chat_id: int, callback_id: str, data: str):
    answer_callback(callback_id)

    if not data.startswith("dl:"):
        return

    format_id = data.split(":", 1)[1]
    pending = pending_requests.get(chat_id)

    if not pending or format_id not in pending["formats"]:
        send_message(chat_id, "⚠️ این درخواست منقضی شده. لطفاً دوباره لینک رو بفرست.")
        return

    url = pending["url"]
    label = pending["formats"][format_id]
    send_message(chat_id, f"⬇️ در حال دانلود کیفیت {label} ...")

    filepath, error_msg = download_format(url, format_id)
    if not filepath:
        send_message(chat_id, f"❌ دانلود ناموفق بود.\n\nخطا:\n{error_msg[:300]}")
        return

    send_message(chat_id, "⬆️ دانلود تموم شد، در حال ارسال...")
    caption = os.path.splitext(os.path.basename(filepath))[0]
    ok = send_video(chat_id, filepath, caption=caption)

    if not ok:
        send_message(chat_id, "❌ ارسال ویدیو ناموفق بود.")

    try:
        os.remove(filepath)
    except OSError:
        pass

    pending_requests.pop(chat_id, None)


def main():
    print("🤖 ربات در حال اجراست... (برای توقف Ctrl+C بزنید)")
    offset = None

    while True:
        try:
            params = {"timeout": 20}
            if offset is not None:
                params["offset"] = offset

            resp = requests.get(f"{BALE_BASE_URL}/getUpdates", params=params, timeout=30)
            data = resp.json()

            if not data.get("ok"):
                print(f"⚠️ خطا در دریافت آپدیت: {data}")
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1

                if "callback_query" in update:
                    cq = update["callback_query"]
                    chat_id = cq["message"]["chat"]["id"]
                    handle_callback(chat_id, cq["id"], cq.get("data", ""))
                    continue

                message = update.get("message")
                if not message:
                    continue

                chat_id = message["chat"]["id"]
                text = message.get("text", "")
                sender = message.get("from", {}).get("first_name", "کاربر")
                print(f"📩 پیام جدید از {sender} ({chat_id}): {text}")

                handle_message(chat_id, text)

        except requests.exceptions.RequestException as e:
            print(f"⚠️ خطای شبکه: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\n👋 ربات متوقف شد.")
            break


if __name__ == "__main__":
    main()
