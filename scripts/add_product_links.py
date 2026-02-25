"""Add specific product links to existing JA articles using Rakuten API."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import load_config
from pipeline.product_searcher import extract_product_names, search_products_for_article
from pipeline.affiliate_linker import _build_product_cards_ja

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

CONTENT_DIR = Path(__file__).resolve().parent.parent / "site" / "content" / "ja"
SKIP_FILES = {"_index.md", "about.md", "privacy.md"}


def process_article(filepath: Path, config: dict) -> bool:
    """Add product links to a single article. Returns True if modified."""
    text = filepath.read_text(encoding="utf-8")

    # Skip if already has specific product cards
    if "hb.afl.rakuten.co.jp" in text:
        logger.info("SKIP (already has product cards): %s", filepath.name)
        return False

    # Extract product names from article body
    # Split front matter from body
    parts = text.split("---", 2)
    if len(parts) < 3:
        logger.warning("SKIP (no front matter): %s", filepath.name)
        return False

    body = parts[2].strip()
    product_names = extract_product_names(body, "ja")

    if not product_names:
        logger.info("SKIP (no product names found): %s", filepath.name)
        return False

    logger.info("Found products in %s: %s", filepath.name, product_names)

    # Search Rakuten API
    products = search_products_for_article(product_names, config)
    if not products:
        logger.info("SKIP (no Rakuten results): %s", filepath.name)
        return False

    # Build product cards section
    cards = _build_product_cards_ja(products)

    # Remove old generic Rakuten search link if present
    # (keeping Amazon links and A8 links)
    import re
    # Remove old generic "楽天市場で探す" line with moshimo link
    body = re.sub(
        r'\n*\*\*\[[^\]]*楽天市場で探す[^\]]*\]\(https://af\.moshimo\.com/[^)]*\)\*\*\s*',
        '',
        body,
    )

    # Insert product cards before the existing おすすめ商品 section or at the end
    if "## おすすめ商品" in body:
        # Replace existing おすすめ商品 section
        body = re.sub(
            r'---\s*\n\n## おすすめ商品.*?(?=\n## |\n\*当サイト|\Z)',
            '',
            body,
            flags=re.DOTALL,
        )
        # Also remove the disclosure text if it's orphaned
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
                # Rate limit: wait between articles that made API calls
                time.sleep(2)
            else:
                skipped += 1
        except Exception as e:
            logger.error("ERROR processing %s: %s", filepath.name, e)
            skipped += 1

    logger.info("Done! Updated: %d, Skipped: %d", updated, skipped)


if __name__ == "__main__":
    main()
