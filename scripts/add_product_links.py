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
    search_products_by_keyword,
    search_products_for_article,
)
from pipeline.affiliate_linker import _build_product_cards_ja

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

CONTENT_DIR = Path(__file__).resolve().parent.parent / "site" / "content" / "ja"
SKIP_FILES = {"_index.md", "about.md", "privacy.md"}


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


def process_article(filepath: Path, config: dict) -> bool:
    """Add product links to a single article. Returns True if modified."""
    text = filepath.read_text(encoding="utf-8")

    # Skip if already has product cards WITH images
    has_rakuten = "hb.afl.rakuten.co.jp" in text
    has_images = "[![" in text and has_rakuten
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

    # Strategy 2: Fallback to keyword-based search (uses product_searcher.py)
    if not products:
        keyword = _extract_keyword_from_frontmatter(text)
        if keyword:
            logger.info("Trying keyword-based search for %s: '%s'", filepath.name, keyword)
            products = search_products_by_keyword(keyword, config)

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
