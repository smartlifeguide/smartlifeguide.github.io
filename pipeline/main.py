"""Main pipeline orchestrator for the automated blog system."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from pipeline.affiliate_linker import insert_affiliate_links
from pipeline.article_generator import generate_article
from pipeline.config import get_data_path, load_config
from pipeline.image_fetcher import fetch_image
from pipeline.internal_linker import insert_internal_links, update_existing_articles
from pipeline.keyword_researcher import get_unused_keyword, research_keywords
from pipeline.publisher import get_published_slugs, git_commit_and_push, publish_article

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_niches() -> list[dict]:
    """Load niche definitions from data/niches.json."""
    niches_path = get_data_path("niches.json")
    try:
        with open(niches_path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("niches", [])
    except (FileNotFoundError, json.JSONDecodeError):
        logger.error("Failed to load niches.json")
        return []


def run_pipeline(skip_research: bool = False, skip_git: bool = False) -> None:
    """Execute the full article generation pipeline.

    Steps:
    1. Load config and niches
    2. Research keywords (unless skipped)
    3. Select unused keywords for each language
    4. Generate articles via Gemini API
    5. Insert affiliate links
    6. Publish to Hugo content directory
    7. Git commit and push (unless skipped)
    """
    logger.info("=== Starting blog generation pipeline ===")

    config = load_config()
    niches = load_niches()

    if not niches:
        logger.error("No niches configured. Add niches to data/niches.json")
        sys.exit(1)

    # Step 1: Keyword research
    if not skip_research:
        logger.info("--- Step 1: Keyword Research ---")
        research_keywords(niches, config)
    else:
        logger.info("--- Step 1: Keyword Research (skipped) ---")

    # Step 2: Generate and publish articles
    languages = config.get("site", {}).get("languages", ["ja", "en"])
    published_slugs = get_published_slugs()
    articles_published = 0

    for lang in languages:
        logger.info("--- Step 2: Generating article for %s ---", lang)

        # Find the best unused keyword
        keyword_data = get_unused_keyword(lang, published_slugs)
        if not keyword_data:
            logger.warning("No unused keywords available for %s. Run keyword research.", lang)
            continue

        keyword = keyword_data["keyword"]
        logger.info("Selected keyword: '%s' (score: %s)", keyword, keyword_data.get("score"))

        # Determine niche for this keyword
        niche_name = _find_niche_for_keyword(keyword, niches, lang)

        # Generate article
        article = generate_article(keyword, lang, niche_name, config)
        if not article:
            logger.error("Failed to generate article for '%s'", keyword)
            continue

        # Fetch eye-catch image
        logger.info("--- Step 3: Fetching eye-catch image ---")
        site_dir = Path(__file__).resolve().parent.parent / "site"
        image_path = fetch_image(keyword, lang, config, site_dir)
        if image_path:
            article["image"] = image_path
            logger.info("Image set: %s", image_path)

        # Insert internal links to related articles
        logger.info("--- Step 4: Inserting internal links ---")
        article = insert_internal_links(article, config)

        # Insert affiliate links
        logger.info("--- Step 5: Inserting affiliate links ---")
        article = insert_affiliate_links(article, config)

        # Publish
        logger.info("--- Step 6: Publishing article ---")
        success = publish_article(article, config)
        if success:
            articles_published += 1
            published_slugs.add(keyword_data["keyword"].lower().replace(" ", "-"))
            logger.info("Successfully published: %s", article["front_matter"].get("title"))

            # Update existing articles with links to the new article
            logger.info("--- Step 7: Updating existing articles with internal links ---")
            updated = update_existing_articles(article, config)
            if updated:
                logger.info("Updated %d existing article(s) with internal links", updated)
        else:
            logger.error("Failed to publish article for '%s'", keyword)

    # Step 8: Git commit and push
    if not skip_git and articles_published > 0:
        logger.info("--- Step 8: Git commit and push ---")
        git_commit_and_push(config)
    elif articles_published == 0:
        logger.warning("No articles were published in this run")

    logger.info(
        "=== Pipeline complete. Published %d article(s) ===",
        articles_published,
    )


def _find_niche_for_keyword(keyword: str, niches: list[dict], lang: str) -> str:
    """Find the best matching niche name for a keyword."""
    kw_lower = keyword.lower()
    lang_key = f"seed_keywords_{lang}"
    name_key = f"name_{lang}"

    for niche in niches:
        seeds = niche.get(lang_key, [])
        for seed in seeds:
            if seed.lower() in kw_lower or kw_lower in seed.lower():
                return niche.get(name_key, niche.get("id", "general"))

    # Default to first niche
    if niches:
        return niches[0].get(f"name_{lang}", niches[0].get("id", "general"))
    return "general"


def main() -> None:
    """Entry point for the pipeline."""
    import argparse

    parser = argparse.ArgumentParser(description="Automated blog generation pipeline")
    parser.add_argument(
        "--skip-research",
        action="store_true",
        help="Skip keyword research step",
    )
    parser.add_argument(
        "--skip-git",
        action="store_true",
        help="Skip git commit and push",
    )
    args = parser.parse_args()

    run_pipeline(skip_research=args.skip_research, skip_git=args.skip_git)


if __name__ == "__main__":
    main()
