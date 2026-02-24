"""Product search module using Rakuten Ichiba API + Moshimo affiliate links."""

from __future__ import annotations

import logging
import os
import time
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

RAKUTEN_API_URL = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"

MOSHIMO_BASE = (
    "https://af.moshimo.com/af/c/click?a_id={a_id}"
    "&p_id=54&pc_id=54&pl_id=616"
    "&url={encoded_url}"
)


def search_product(keyword: str, app_id: str) -> dict | None:
    """Search Rakuten Ichiba for a product and return the top result.

    Returns dict with: name, price, url, image_url, or None if not found.
    """
    try:
        resp = requests.get(
            RAKUTEN_API_URL,
            params={
                "applicationId": app_id,
                "keyword": keyword,
                "hits": 3,
                "formatVersion": 2,
                "sort": "standard",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.warning("Rakuten API request failed for '%s'", keyword)
        return None

    items = data.get("Items", [])
    if not items:
        logger.info("No Rakuten results for '%s'", keyword)
        return None

    item = items[0]
    return {
        "name": item.get("itemName", ""),
        "price": item.get("itemPrice", 0),
        "url": item.get("itemUrl", ""),
        "image_url": (item.get("mediumImageUrls") or [""])[0] if item.get("mediumImageUrls") else "",
    }


def build_moshimo_link(product_url: str, a_id: str) -> str:
    """Wrap a Rakuten product URL with Moshimo affiliate tracking."""
    return MOSHIMO_BASE.format(
        a_id=a_id,
        encoded_url=quote(product_url, safe=""),
    )


def search_products_for_article(
    product_keywords: list[str],
    config: dict,
) -> list[dict]:
    """Search Rakuten for each product keyword and return results with Moshimo links.

    Returns list of dicts: {name, price, url, affiliate_url, image_url}
    """
    app_id = config.get("affiliate", {}).get("rakuten_app_id", "")
    if not app_id:
        app_id = os.environ.get("RAKUTEN_APP_ID", "")
    if not app_id:
        logger.warning("No Rakuten App ID configured, skipping product search")
        return []

    a_id = config.get("affiliate", {}).get("moshimo_rakuten_a_id", "")
    if not a_id:
        logger.warning("No Moshimo a_id configured, skipping product search")
        return []

    results = []
    for kw in product_keywords[:5]:  # Max 5 products per article
        product = search_product(kw, app_id)
        if product and product["url"]:
            product["affiliate_url"] = build_moshimo_link(product["url"], a_id)
            results.append(product)
            logger.info("Found product: %s (¥%s)", product["name"][:50], product["price"])
        # Rate limit: 1 request per second
        time.sleep(1)

    return results
