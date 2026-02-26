"""Add specific product links to existing JA articles using Rakuten API."""

from __future__ import annotations

import logging
import re
import sys
import time
import yaml
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import load_config
from pipeline.product_searcher import (
    extract_product_names,
    search_product,
    search_products_for_article,
)
from pipeline.affiliate_linker import _build_product_cards_ja

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

CONTENT_DIR = Path(__file__).resolve().parent.parent / "site" / "content" / "ja"
SKIP_FILES = {"_index.md", "about.md", "privacy.md"}

# Minimum prices by category to filter out accessories (search by keyword mode)
_MIN_PRICES = {
    "掃除機": 15000,
    "ロボット掃除機": 20000,
    "洗濯機": 30000,
    "ドラム式洗濯機": 50000,
    "食洗機": 15000,
    "空気清浄機": 10000,
    "加湿器": 3000,
    "除湿機": 8000,
    "マットレス": 5000,
    "体重計": 2000,
    "血圧計": 2000,
    "肩こり": 500,
    "家計簿": 500,
}

# Keywords that are not product-searchable (services, concepts)
_SKIP_KEYWORDS = [
    "節約", "方法", "コツ", "格安sim", "保険", "学資", "教育費",
    "介護", "見守り", "塾", "習い事", "お小遣い", "ふるさと納税",
    "ポイ活", "通信教育",
]


def _extract_keyword_from_frontmatter(text: str) -> str:
    """Extract the keyword from article front matter."""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    try:
        fm = yaml.safe_load(parts[1])
        keywords = fm.get("keywords", [])
        if keywords:
            return keywords[0]
    except Exception:
        pass
    return ""


def _get_min_price(keyword: str) -> int:
    """Get minimum price filter for a keyword to exclude accessories."""
    for pattern, price in _MIN_PRICES.items():
        if pattern in keyword:
            return price
    return 3000  # Default: skip items under ¥3000


def _is_product_keyword(keyword: str) -> bool:
    """Check if the keyword is something that can yield product results."""
    for skip in _SKIP_KEYWORDS:
        if skip in keyword:
            return False
    return True


def _search_by_keyword(keyword: str, config: dict) -> list[dict]:
    """Search Rakuten using article keyword with price filtering."""
    aff_cfg = config.get("affiliate", {})
    application_id = aff_cfg.get("rakuten_application_id", "")
    access_key = aff_cfg.get("rakuten_access_key", "")
    if not access_key:
        import os
        access_key = os.environ.get("RAKUTEN_ACCESS_KEY", "")
    affiliate_id = aff_cfg.get("rakuten_affiliate_id", "")

    if not application_id or not access_key:
        return []

    # Clean up keyword for search (remove おすすめ, 比較, etc.)
    search_kw = keyword
    for remove in ["おすすめ", "比較", "選び方", "ランキング", "口コミ", "レビュー"]:
        search_kw = search_kw.replace(remove, "")
    search_kw = search_kw.strip()

    if not search_kw or len(search_kw) < 2:
        return []

    min_price = _get_min_price(keyword)
    params = {
        "applicationId": application_id,
        "accessKey": access_key,
        "keyword": search_kw,
        "hits": 10,
        "formatVersion": 2,
        "sort": "-reviewCount",  # Sort by review count (popular products)
        "minPrice": min_price,
    }
    if affiliate_id:
        params["affiliateId"] = affiliate_id

    headers = {
        "User-Agent": "SmartLifeGuide",
        "Origin": "https://smartlifeguide.github.io",
    }

    import requests
    try:
        resp = requests.get(
            "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601",
            params=params,
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("Rakuten API failed for keyword '%s': %s", search_kw, e)
        return []

    items = data.get("Items", [])
    if not items:
        return []

    from pipeline.product_searcher import _pick_best_item, _SKIP_WORDS, build_moshimo_link

    results = []
    moshimo_a_id = aff_cfg.get("moshimo_rakuten_a_id", "")

    for item in items:
        name = item.get("itemName", "")
        if any(w in name for w in _SKIP_WORDS):
            continue

        product = {
            "name": name,
            "price": item.get("itemPrice", 0),
            "url": item.get("itemUrl", ""),
            "affiliate_url": item.get("affiliateUrl", ""),
            "image_url": (item.get("mediumImageUrls") or [""])[0] if item.get("mediumImageUrls") else "",
        }

        if not product.get("affiliate_url") and moshimo_a_id:
            product["affiliate_url"] = build_moshimo_link(product["url"], moshimo_a_id)

        if product.get("affiliate_url"):
            results.append(product)

        if len(results) >= 3:
            break

    return results


def process_article(filepath: Path, config: dict) -> bool:
    """Add product links to a single article. Returns True if modified."""
    text = filepath.read_text(encoding="utf-8")

    # Skip if already has product cards WITH images
    has_rakuten = "hb.afl.rakuten.co.jp" in text
    has_images = "[![" in text and "hb.afl.rakuten.co.jp" in text
    if has_rakuten and has_images:
        logger.info("SKIP (already has product cards with images): %s", filepath.name)
        return False

    # Split front matter from body
    parts = text.split("---", 2)
    if len(parts) < 3:
        logger.warning("SKIP (no front matter): %s", filepath.name)
        return False

    body = parts[2].strip()

    # Strategy 1: Extract specific product names from body
    product_names = extract_product_names(body, "ja")
    products = []

    if product_names:
        logger.info("Found product names in %s: %s", filepath.name, product_names)
        products = search_products_for_article(product_names, config)

    # Strategy 2: Fallback to keyword-based search
    if not products:
        keyword = _extract_keyword_from_frontmatter(text)
        if keyword and _is_product_keyword(keyword):
            logger.info("Trying keyword-based search for %s: '%s'", filepath.name, keyword)
            products = _search_by_keyword(keyword, config)

    if not products:
        logger.info("SKIP (no products found): %s", filepath.name)
        return False

    # Build product cards section
    cards = _build_product_cards_ja(products)

    # Remove old generic Rakuten search link if present
    body = re.sub(
        r'\n*\*\*\[[^\]]*楽天市場で探す[^\]]*\]\(https://af\.moshimo\.com/[^)]*\)\*\*\s*',
        '',
        body,
    )

    # Replace existing おすすめ商品 section if present
    if "## おすすめ商品" in body:
        body = re.sub(
            r'---\s*\n\n## おすすめ商品.*?(?=\n## |\n\*当サイト|\Z)',
            '',
            body,
            flags=re.DOTALL,
        )
        body = re.sub(
            r'\n*\*当サイトはアフィリエイトプログラムに参加しています。[^*]*\*\s*',
            '',
            body,
        )
        body = body.rstrip()

    # Append product cards
    new_body = body.rstrip() + "\n\n" + cards

    # Rebuild full file
    new_text = "---" + parts[1] + "---\n\n" + new_body + "\n"
    filepath.write_text(new_text, encoding="utf-8")
    logger.info("UPDATED: %s (%d products)", filepath.name, len(products))
    return True


def main():
    config = load_config()
    articles = sorted(
        f for f in CONTENT_DIR.glob("*.md") if f.name not in SKIP_FILES
    )
    logger.info("Processing %d articles...", len(articles))

    updated = 0
    skipped = 0
    for i, filepath in enumerate(articles):
        logger.info("[%d/%d] %s", i + 1, len(articles), filepath.name)
        try:
            if process_article(filepath, config):
                updated += 1
                time.sleep(2)
            else:
                skipped += 1
        except Exception as e:
            logger.error("ERROR processing %s: %s", filepath.name, e)
            skipped += 1

    logger.info("Done! Updated: %d, Skipped: %d", updated, skipped)


if __name__ == "__main__":
    main()
