"""
ربات بله: دانلود از یوتیوب با انتخاب کیفیت + تقسیم RAR چندپارتی
--------------------------------------------------------------------
پیش‌نیازها:
    pip install yt-dlp requests
    + ffmpeg و rar باید روی سیستم نصب باشن (nixpacks.toml این کار رو
      روی Railway انجام می‌ده)

نحوه کار:
    1. کاربر لینک یوتیوب می‌فرسته
    2. ربات همه‌ی کیفیت‌های موجود (حتی سنگین‌ها) رو با حجم تخمینی نشون می‌ده
    3. کاربر کیفیت مورد نظر رو انتخاب می‌کنه
    4. ویدیو دانلود و (در صورت نیاز) با ffmpeg ترکیب میشه
    5. اگه حجم نهایی از سقف مجاز بله بیشتر بود، با ابزار rar به چند پارت
       تقسیم و همه‌ی پارت‌ها پشت‌سرهم به‌عنوان فایل (document) ارسال میشن
"""

import os
import re
import glob
import time
import subprocess
import requests
import yt_dlp

# ============ تنظیمات ============
BALE_TOKEN = "1624551307:sXvFHJ0-5wGM-VwHbGqW7DuLH0DUHNKZfP8"
BALE_BASE_URL = f"https://tapi.bale.ai/bot{BALE_TOKEN}"

DOWNLOAD_DIR = "downloads"
MAX_SIZE_MB = 45          # سقف حجم مجاز برای هر پارت/فایل ارسالی به بله
RAR_VOLUME_MB = 40        # حجم هر پارت RAR (کمی کمتر از سقف برای اطمینان)
POLL_INTERVAL_SECONDS = 2

YOUTUBE_URL_PATTERN = re.compile(
    r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w\-]+[^\s]*"
)


def base_ydl_opts() -> dict:
    return {
        "quiet": True,
        "noplaylist": True,
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    }


# حافظه موقت: chat_id -> {"url": ..., "formats": {key: {"format": ..., "label": ...}}}
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
    همه‌ی کیفیت‌های موجود (progressive و adaptive) رو با حجم تخمینی برمی‌گردونه،
    بدون فیلتر کردن بر اساس سقف حجم (چون قراره سنگین‌ها رو با RAR تقسیم کنیم).
    """
    with yt_dlp.YoutubeDL(base_ydl_opts()) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = info.get("formats", [])

    audio_formats = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") != "none"]
    best_audio = max(audio_formats, key=lambda f: f.get("abr") or 0, default=None)
    audio_size = (best_audio.get("filesize") or best_audio.get("filesize_approx") or 0) if best_audio else 0

    best_by_height = {}

    for f in formats:
        height = f.get("height")
        if not height:
            continue

        is_progressive = f.get("vcodec") != "none" and f.get("acodec") != "none"
        is_video_only = f.get("vcodec") != "none" and f.get("acodec") == "none"

        if is_progressive and f.get("ext") == "mp4":
            size = f.get("filesize") or f.get("filesize_approx") or 0
            selector = f["format_id"]
        elif is_video_only and best_audio and f.get("ext") == "mp4":
            video_size = f.get("filesize") or f.get("filesize_approx") or 0
            size = (video_size + audio_size) if video_size else 0
            selector = f"{f['format_id']}+{best_audio['format_id']}"
        else:
            continue

        if height not in best_by_height or size > best_by_height[height][1]:
            best_by_height[height] = (selector, size)

    result = [{"format": selector, "height": h, "size": size} for h, (selector, size) in best_by_height.items()]
    result.sort(key=lambda x: x["height"], reverse=True)
    return result, info.get("title", "video")


def download_format(url: str, format_selector: str) -> tuple:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    opts = base_ydl_opts()
    opts.update({
        "format": format_selector,
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s_%(height)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": False,
    })
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
            if not os.path.exists(filepath):
                base, _ = os.path.splitext(filepath)
                filepath = base + ".mp4"
            return filepath, ""
    except Exception as e:
        print(f"❌ خطا در دانلود: {e}")
        return None, str(e)


def split_into_rar_parts(filepath: str) -> list:
    """فایل رو با rar به چند پارت (.part1.rar, .part2.rar, ...) تقسیم می‌کنه."""
    base_name = os.path.splitext(filepath)[0]
    rar_path = base_name + ".rar"

    cmd = [
        "rar", "a",
        f"-v{RAR_VOLUME_MB}m",  # حجم هر پارت
        "-ep1",                  # مسیر فایل رو داخل آرشیو ذخیره نکن
        "-m0",                   # بدون فشرده‌سازی (سریع‌تر، چون ویدیو از قبل فشرده‌ست)
        rar_path,
        filepath,
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    parts = sorted(glob.glob(base_name + ".part*.rar"))
    return parts


def send_document(chat_id: int, filepath: str, caption: str = "") -> bool:
    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                f"{BALE_BASE_URL}/sendDocument",
                data={"chat_id": chat_id, "caption": caption},
                files={"document": f},
                timeout=300,
            )
        return bool(resp.json().get("ok"))
    except Exception as e:
        print(f"❌ خطا در ارسال فایل: {e}")
        return False


def send_video(chat_id: int, filepath: str, caption: str = "") -> bool:
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
        send_message(chat_id, "سلامم! 👋 لینک ویدیوی یوتیوب رو برام بفرست تا کیفیت‌های موجود رو نشونت بدم.")
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
        send_message(chat_id, "❌ هیچ کیفیتی برای این ویدیو پیدا نشد.")
        return

    format_map = {}
    buttons = []
    for i, q in enumerate(qualities):
        key = str(i)
        size_mb = (q["size"] / (1024 * 1024)) if q["size"] else 0
        note = " 📦 چندپارتی" if size_mb > MAX_SIZE_MB else ""
        label = f"{q['height']}p - {format_size(q['size'])}{note}"
        format_map[key] = {"format": q["format"], "label": label}
        buttons.append([{"text": label, "callback_data": f"dl:{key}"}])

    pending_requests[chat_id] = {"url": url, "formats": format_map}

    send_message(
        chat_id,
        f"🎬 {title}\n\nکیفیت مورد نظر رو انتخاب کن:\n(کیفیت‌های با علامت 📦 به‌صورت RAR چندپارتی ارسال میشن)",
        reply_markup={"inline_keyboard": buttons},
    )


def handle_callback(chat_id: int, callback_id: str, data: str):
    answer_callback(callback_id)

    if not data.startswith("dl:"):
        return

    key = data.split(":", 1)[1]
    pending = pending_requests.get(chat_id)

    if not pending or key not in pending["formats"]:
        send_message(chat_id, "⚠️ این درخواست منقضی شده. لطفاً دوباره لینک رو بفرست.")
        return

    url = pending["url"]
    chosen = pending["formats"][key]
    send_message(chat_id, f"⬇️ در حال دانلود کیفیت {chosen['label']} ...")

    filepath, error_msg = download_format(url, chosen["format"])
    if not filepath:
        send_message(chat_id, f"❌ دانلود ناموفق بود.\n\nخطا:\n{error_msg[:300]}")
        return

    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    caption = os.path.splitext(os.path.basename(filepath))[0]

    if size_mb <= MAX_SIZE_MB:
        send_message(chat_id, "⬆️ دانلود تموم شد، در حال ارسال...")
        ok = send_video(chat_id, filepath, caption=caption)
        if not ok:
            send_message(chat_id, "❌ ارسال ویدیو ناموفق بود.")
    else:
        send_message(chat_id, f"📦 حجم فایل {size_mb:.1f} مگابایته، در حال تقسیم به چند پارت RAR...")
        try:
            parts = split_into_rar_parts(filepath)
        except subprocess.CalledProcessError as e:
            send_message(chat_id, f"❌ خطا در ساخت RAR: {e}")
            _cleanup(filepath)
            pending_requests.pop(chat_id, None)
            return

        if not parts:
            send_message(chat_id, "❌ تقسیم فایل ناموفق بود.")
        else:
            send_message(chat_id, f"⬆️ در حال ارسال {len(parts)} پارت...")
            for i, part in enumerate(parts, 1):
                ok = send_document(chat_id, part, caption=f"{caption} - پارت {i}/{len(parts)}")
                if not ok:
                    send_message(chat_id, f"❌ ارسال پارت {i} ناموفق بود.")
                os.remove(part)
            send_message(chat_id, "✅ همه‌ی پارت‌ها ارسال شدن. برای اتصال، همه‌ی پارت‌ها رو کنار هم بذارید و اولی رو با WinRAR باز کنید.")

    _cleanup(filepath)
    pending_requests.pop(chat_id, None)


def _cleanup(filepath: str):
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
