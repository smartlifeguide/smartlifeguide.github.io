"""Publisher module for Hugo content placement and git operations."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from pipeline.config import get_content_dir, get_data_path

logger = logging.getLogger(__name__)


def keyword_to_slug(keyword: str) -> str:
    """Convert a keyword to a URL-friendly slug."""
    slug = unicodedata.normalize("NFKC", keyword.lower())
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = slug.strip("-")
    # Limit length
    if len(slug) > 80:
        slug = slug[:80].rsplit("-", 1)[0]
    return slug


def publish_article(article: dict, config: dict) -> bool:
    """Write an article to the Hugo content directory and record it.

    Returns True on success.
    """
    lang = article["lang"]
    keyword = article["keyword"]
    slug = keyword_to_slug(keyword)
    now = datetime.now(timezone.utc)

    content_dir = get_content_dir(lang)
    filename = f"{slug}.md"
    filepath = content_dir / filename

    # Build full Markdown with front matter
    fm = article["front_matter"]
    date_str = now.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # Build tags and categories lists for front matter
    tags = fm.get("tags", [keyword])
    if isinstance(tags, str):
        tags = [tags]
    categories = fm.get("categories", [])
    if isinstance(categories, str):
        categories = [categories]

    tags_str = ", ".join(f'"{t}"' for t in tags)
    categories_str = ", ".join(f'"{c}"' for c in categories)

    front_matter_lines = [
        "---",
        f'title: "{fm.get("title", keyword)}"',
        f'description: "{fm.get("description", "")}"',
        f"date: {date_str}",
        f'slug: "{slug}"',
        f'language: "{lang}"',
        f'keywords: ["{keyword}"]',
        f"tags: [{tags_str}]",
        f"categories: [{categories_str}]",
        "draft: false",
        "---",
    ]

    content = "\n".join(front_matter_lines) + "\n\n" + article["body"] + "\n"

    filepath.write_text(content, encoding="utf-8")
    logger.info("Published article: %s", filepath)

    # Record in published.json
    _record_published(article, slug, filepath, now)

    return True


def _record_published(article: dict, slug: str, filepath: Path, now: datetime) -> None:
    """Record a published article in the tracking file."""
    published_path = get_data_path("published.json")

    try:
        with open(published_path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"articles": [], "total_count": 0, "last_published": None}

    entry = {
        "slug": slug,
        "keyword": article["keyword"],
        "lang": article["lang"],
        "title": article["front_matter"].get("title", ""),
        "tags": article["front_matter"].get("tags", []),
        "categories": article["front_matter"].get("categories", []),
        "file_path": str(filepath),
        "published_at": now.isoformat(),
        "has_affiliate_links": article.get("has_affiliate_links", False),
    }

    data["articles"].append(entry)
    data["total_count"] = len(data["articles"])
    data["last_published"] = now.isoformat()

    with open(published_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_published_slugs() -> set[str]:
    """Get the set of all published article slugs."""
    published_path = get_data_path("published.json")
    try:
        with open(published_path, encoding="utf-8") as f:
            data = json.load(f)
        return {a["slug"] for a in data.get("articles", [])}
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def git_commit_and_push(config: dict) -> bool:
    """Stage, commit, and push new articles to the repository.

    Returns True on success.
    """
    if not config.get("publishing", {}).get("auto_commit", True):
        logger.info("Auto-commit disabled, skipping git operations")
        return True

    try:
        # Stage content and data files
        subprocess.run(
            ["git", "add", "site/content/", "data/"],
            check=True,
            capture_output=True,
        )

        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
        )
        if result.returncode == 0:
            logger.info("No changes to commit")
            return True

        # Commit
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        msg = f"Auto-publish articles ({now})"
        subprocess.run(
            ["git", "commit", "-m", msg],
            check=True,
            capture_output=True,
        )

        # Push
        branch = config.get("publishing", {}).get("branch", "main")
        subprocess.run(
            ["git", "push", "origin", branch],
            check=True,
            capture_output=True,
        )

        logger.info("Git commit and push successful")
        return True

    except subprocess.CalledProcessError:
        logger.exception("Git operation failed")
        return False
