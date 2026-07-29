import os
import logging
import asyncio

from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Application, MessageHandler, filters, ContextTypes

from aliexpress_api import (
    extract_product_id,
    resolve_short_link,
    get_product_details,
    generate_affiliate_link,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("aliexpress-bot")

# ---------- متغيرات البيئة (تُضبط في Render) ----------
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALIEXPRESS_APP_KEY = os.environ["ALIEXPRESS_APP_KEY"]
ALIEXPRESS_APP_SECRET = os.environ["ALIEXPRESS_APP_SECRET"]
ALIEXPRESS_TRACKING_ID = os.environ["ALIEXPRESS_TRACKING_ID"]

# Render يضبط هذا المتغير تلقائياً باسم الدومين الخاص بالخدمة
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBHOOK_PATH = "/webhook"
PORT = int(os.environ.get("PORT", 10000))

flask_app = Flask(__name__)
telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()


def build_reply(product_id: str, source_url: str) -> str:
    data = get_product_details(
        product_id,
        ALIEXPRESS_APP_KEY,
        ALIEXPRESS_APP_SECRET,
        ALIEXPRESS_TRACKING_ID,
    )
    try:
        result = data["aliexpress_affiliate_productdetail_get_response"]["resp_result"]["result"]
        products = result["products"]["product"]
        product = products[0] if isinstance(products, list) else products
    except (KeyError, IndexError, TypeError):
        # فشل جلب التفاصيل، نحاول على الأقل توليد رابط أفلييت عادي
        link_data = generate_affiliate_link(
            source_url, ALIEXPRESS_APP_KEY, ALIEXPRESS_APP_SECRET, ALIEXPRESS_TRACKING_ID
        )
        try:
            promo = link_data["aliexpress_affiliate_link_generate_response"]["resp_result"]["result"][
                "promotion_links"
            ]["promotion_link"][0]["promotion_link"]
            return f"⚠️ ما قدرتش نجيب تفاصيل الخصم، بصح هذا رابط الأفلييت:\n{promo}"
        except Exception:
            return "❌ ما قدرتش نجيب معلومات على هذا المنتج، تأكد من الرابط وحاول مرة أخرى."

    title = product.get("product_title", "منتج")
    sale_price = product.get("target_sale_price", "؟")
    original_price = product.get("target_original_price", "؟")
    discount = product.get("discount", "0")
    promo_link = product.get("promotion_link", source_url)
    image = product.get("product_main_image_url", "")

    text = (
        f"🛍️ {title}\n\n"
        f"💰 السعر بعد الخصم: {sale_price}\n"
        f"🔻 السعر الأصلي: {original_price}\n"
        f"🔥 نسبة الخصم: {discount}%\n\n"
        f"🔗 رابط الشراء (أفلييت):\n{promo_link}"
    )
    if image:
        text = f"{image}\n\n{text}"
    return text


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return

    text = message.text.strip()
    if "aliexpress" not in text.lower():
        return

    url = text
    if "a.aliexpress.com" in url or "s.click.aliexpress.com" in url:
        url = resolve_short_link(url)

    product_id = extract_product_id(url)
    if not product_id:
        await message.reply_text("ما قدرتش نلقى رقم المنتج في هذا الرابط 🤔")
        return

    await message.reply_text("🔎 قاعد نبحث على أحسن خصم لهذا المنتج...")
    reply = build_reply(product_id, url)
    await message.reply_text(reply, disable_web_page_preview=False)


telegram_app.add_handler(
    MessageHandler(filters.TEXT & (filters.ChatType.PRIVATE | filters.ChatType.GROUPS | filters.UpdateType.CHANNEL_POST), handle_message)
)


@flask_app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    asyncio.run(telegram_app.process_update(update))
    return "OK"


@flask_app.route("/", methods=["GET"])
def health_check():
    # هذا المسار يُستخدم من cron-job.org لإبقاء الخدمة صاحية على خطة Render المجانية
    return "Bot is running ✅"


async def setup_webhook():
    if not RENDER_EXTERNAL_URL:
        log.warning("RENDER_EXTERNAL_URL غير موجود - تأكد أنك تشغل هذا على Render")
        return
    webhook_url = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"
    bot = Bot(TELEGRAM_BOT_TOKEN)
    await bot.set_webhook(webhook_url)
    log.info(f"تم ضبط الـ webhook على: {webhook_url}")


if __name__ == "__main__":
    asyncio.run(telegram_app.initialize())
    asyncio.run(setup_webhook())
    flask_app.run(host="0.0.0.0", port=PORT)
