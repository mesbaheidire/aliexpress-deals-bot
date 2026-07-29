"""
اتصال مبسّط بـ AliExpress Affiliate API (Open Platform / TOP protocol).
يحتاج: APP_KEY, APP_SECRET, TRACKING_ID من https://portals.aliexpress.com/ (Affiliate -> API)
"""

import hashlib
import hmac
import time
import re
import requests

GATEWAY_URL = "https://api-sg.aliexpress.com/sync"


def _sign(params: dict, app_secret: str) -> str:
    """توقيع HMAC-SHA256 حسب بروتوكول TOP الذي تستخدمه علي إكسبريس."""
    sorted_keys = sorted(params.keys())
    concat_str = "".join(f"{k}{params[k]}" for k in sorted_keys)
    signature = hmac.new(
        app_secret.encode("utf-8"),
        concat_str.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest().upper()
    return signature


def _call_api(method: str, app_key: str, app_secret: str, business_params: dict) -> dict:
    params = {
        "app_key": app_key,
        "method": method,
        "sign_method": "sha256",
        "timestamp": str(int(time.time() * 1000)),
        "v": "2.0",
        "format": "json",
    }
    params.update(business_params)
    params["sign"] = _sign(params, app_secret)

    resp = requests.get(GATEWAY_URL, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def extract_product_id(text: str) -> str | None:
    """
    يحاول استخراج رقم المنتج من رابط علي إكسبريس (روابط طويلة).
    إذا كان الرابط قصير (a.aliexpress.com/...) يجب فك تشفيره أولاً بدالة resolve_short_link.
    """
    match = re.search(r"/item/(\d+)\.html", text) or re.search(r"[?&]productId=(\d+)", text)
    if match:
        return match.group(1)
    return None


def resolve_short_link(url: str) -> str:
    """يفك أي رابط مختصر (a.aliexpress.com أو s.click...) لآخر رابط بعد التحويلات."""
    try:
        resp = requests.get(url, allow_redirects=True, timeout=10)
        return resp.url
    except requests.RequestException:
        return url


def get_product_details(product_id: str, app_key: str, app_secret: str, tracking_id: str,
                         target_currency: str = "USD", target_language: str = "AR",
                         ship_to_country: str = "DZ") -> dict:
    """يجلب تفاصيل المنتج: السعر الأصلي، سعر الخصم، نسبة الخصم."""
    business_params = {
        "product_ids": product_id,
        "tracking_id": tracking_id,
        "target_currency": target_currency,
        "target_language": target_language,
        "ship_to_country": ship_to_country,
        "fields": "product_id,product_title,product_main_image_url,target_sale_price,"
                  "target_original_price,discount,promotion_link,evaluate_rate,lastest_volume",
    }
    return _call_api("aliexpress.affiliate.productdetail.get", app_key, app_secret, business_params)


def generate_affiliate_link(source_url: str, app_key: str, app_secret: str, tracking_id: str) -> dict:
    """يولّد رابط أفلييت (عمولة) مباشرة من رابط منتج عادي."""
    business_params = {
        "promotion_link_type": "0",
        "source_values": source_url,
        "tracking_id": tracking_id,
    }
    return _call_api("aliexpress.affiliate.link.generate", app_key, app_secret, business_params)
