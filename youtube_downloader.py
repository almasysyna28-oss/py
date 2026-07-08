"""
دانلود ویدیو از یوتیوب و ارسال خودکار به بله (Bale)
------------------------------------------------------
پیش‌نیازها:
    pip install yt-dlp requests

نکته مهم: API بازوهای بله (مثل تلگرام) معمولاً برای آپلود مستقیم فایل
سقف حجمی حدود ۵۰ مگابایت داره. برای ویدیوهای بزرگ‌تر کیفیت رو پایین بیارید.
"""

import os
import requests
import yt_dlp

# ============ تنظیمات بله ============
BALE_TOKEN = "1624551307:sXvFHJ0-5wGM-VwHbGqW7DuLH0DUHNKZfP8"
BALE_BASE_URL = f"https://tapi.bale.ai/bot{BALE_TOKEN}"
BALE_CHAT_ID = 536174723  # chat_id گفتگوی خصوصی شما با بازو

DOWNLOAD_DIR = "downloads"
MAX_SIZE_MB = 45  # کمی کمتر از سقف رایج ۵۰ مگابایتی برای اطمینان


def download_from_youtube(url: str, quality: str = "480") -> str | None:
    """دانلود ویدیو از یوتیوب و بازگرداندن مسیر فایل دانلود شده."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    ydl_opts = {
        "format": f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}]",
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title).80s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        # اگه خطای "Sign in to confirm you're not a bot" گرفتید،
        # خط پایین رو از کامنت خارج کنید و نام مرورگری که توش
        # لاگین یوتیوب هستید رو بذارید: chrome, firefox, edge, brave
        # "cookiesfrombrowser": ("chrome",),
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
            if not os.path.exists(filepath):
                base, _ = os.path.splitext(filepath)
                filepath = base + ".mp4"
            return filepath
    except Exception as e:
        print(f"❌ خطا در دانلود: {e}")
        return None


def send_file_to_bale(filepath: str, caption: str = "") -> bool:
    """ارسال فایل ویدیویی به چت بله از طریق متد sendVideo (یا sendDocument برای فایل‌های غیر ویدیویی)"""
    size_mb = os.path.getsize(filepath) / (1024 * 1024)

    if size_mb > MAX_SIZE_MB:
        print(f"⚠️  حجم فایل {size_mb:.1f} مگابایته و ممکنه بیشتر از سقف مجاز بله باشه.")
        print("    پیشنهاد میشه کیفیت پایین‌تری برای دانلود انتخاب کنید.")

    print(f"⬆️  در حال ارسال فایل ({size_mb:.1f} MB) به بله...")

    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                f"{BALE_BASE_URL}/sendVideo",
                data={"chat_id": BALE_CHAT_ID, "caption": caption},
                files={"video": f},
                timeout=300,
            )
        result = resp.json()
        if result.get("ok"):
            print("✅ فایل با موفقیت به بله ارسال شد.")
            return True
        else:
            print(f"❌ خطای بله: {result}")
            return False
    except Exception as e:
        print(f"❌ خطا در ارسال فایل: {e}")
        return False


def main():
    url = input("🔗 لینک ویدیوی یوتیوب رو وارد کنید: ").strip()
    if not url:
        print("❌ لینکی وارد نشد.")
        return

    quality = input("🎞️  کیفیت (144/240/360/480/720) [پیش‌فرض 480]: ").strip() or "480"

    print("\n⬇️  در حال دانلود از یوتیوب...")
    filepath = download_from_youtube(url, quality=quality)

    if not filepath:
        print("عملیات متوقف شد.")
        return

    print(f"✅ دانلود کامل شد: {filepath}")

    caption = os.path.splitext(os.path.basename(filepath))[0]
    send_file_to_bale(filepath, caption=caption)


if __name__ == "__main__":
    main()
