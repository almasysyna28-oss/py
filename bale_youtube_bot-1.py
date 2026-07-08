"""
ربات بله: هر کسی لینک یوتیوب بفرسته، ویدیو رو دانلود و براش ارسال می‌کنه
------------------------------------------------------------------------
پیش‌نیازها:
    pip install yt-dlp requests

نحوه کار: این اسکریپت با روش polling (متد getUpdates) هر ۲ ثانیه یک‌بار
پیام‌های جدید رو چک می‌کنه. کاربر لینک یوتیوب رو به ربات می‌فرسته،
ربات دانلود می‌کنه و ویدیو رو در همون چت براش برمی‌گردونه.
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
DEFAULT_QUALITY = "480"
POLL_INTERVAL_SECONDS = 2

YOUTUBE_URL_PATTERN = re.compile(
    r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w\-]+[^\s]*"
)


def send_message(chat_id: int, text: str):
    requests.post(f"{BALE_BASE_URL}/sendMessage", json={"chat_id": chat_id, "text": text})


def download_from_youtube(url: str, quality: str = DEFAULT_QUALITY) -> tuple[str | None, str]:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    ydl_opts = {
        "format": f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}]",
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        # اگه خطای "Sign in to confirm you're not a bot" گرفتید،
        # باید فایل کوکی (cookies.txt) رو آپلود کنید چون روی سرور
        # مرورگری وجود نداره. جزئیات پایین توضیح داده شده.
        "cookiefile": "cookies.txt",
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
            if not os.path.exists(filepath):
                base, _ = os.path.splitext(filepath)
                filepath = base + ".mp4"
            return filepath, ""
    except Exception as e:
        print(f"❌ خطا در دانلود: {e}")
        return None, str(e)


def send_video(chat_id: int, filepath: str, caption: str = "") -> bool:
    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        send_message(chat_id, f"⚠️ حجم ویدیو {size_mb:.1f} مگابایته و بیشتر از سقف مجازه. ارسال ناموفق بود.")
        return False

    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                f"{BALE_BASE_URL}/sendVideo",
                data={"chat_id": chat_id, "caption": caption},
                files={"video": f},
                timeout=300,
            )
        result = resp.json()
        return bool(result.get("ok"))
    except Exception as e:
        print(f"❌ خطا در ارسال فایل: {e}")
        return False


def handle_message(chat_id: int, text: str):
    if not text:
        return

    if text.strip() in ("/start", "start"):
        send_message(chat_id, "سلام! 👋 لینک ویدیوی یوتیوب رو برام بفرست تا دانلودش کنم و برات بفرستم.")
        return

    match = YOUTUBE_URL_PATTERN.search(text)
    if not match:
        send_message(chat_id, "لینک یوتیوب معتبری پیدا نکردم 🤔 لطفاً یک لینک درست بفرست.")
        return

    url = match.group(0)
    send_message(chat_id, "⬇️ در حال دانلود ویدیو... کمی صبر کنید.")

    filepath, error_msg = download_from_youtube(url)
    if not filepath:
        send_message(chat_id, f"❌ دانلود ناموفق بود.\n\nخطا:\n{error_msg[:300]}")
        return

    send_message(chat_id, "⬆️ دانلود تموم شد، در حال ارسال...")
    caption = os.path.splitext(os.path.basename(filepath))[0]
    ok = send_video(chat_id, filepath, caption=caption)

    if ok:
        print(f"✅ ویدیو برای چت {chat_id} ارسال شد.")
    else:
        send_message(chat_id, "❌ ارسال ویدیو ناموفق بود.")

    # پاک کردن فایل بعد از ارسال برای صرفه‌جویی در فضای دیسک
    try:
        os.remove(filepath)
    except OSError:
        pass


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
