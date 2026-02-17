"""Internal linking module for cross-referencing related articles."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from pipeline.config import get_content_dir, get_data_path

logger = logging.getLogger(__name__)

# Maximum related articles to link per article
MAX_RELATED_LINKS = 3


def find_related_articles(
    article: dict,
    published_articles: list[dict],
) -> list[dict]:
    """Find related published articles based on tag overlap and niche similarity.

    Returns a list of related article dicts, sorted by relevance (most related first).
    """
    lang = article.get("lang", "en")
    current_tags = set(_normalize_tags(article.get("front_matter", {}).get("tags", [])))
    current_categories = set(article.get("front_matter", {}).get("categories", []))
    current_keyword = article.get("keyword", "").lower()

    scored: list[tuple[float, dict]] = []

    for pub in published_articles:
        # Only link to articles in the same language
        if pub.get("lang") != lang:
            continue
        # Don't link to itself
        if pub.get("keyword", "").lower() == current_keyword:
            continue

        pub_tags = set(_normalize_tags(pub.get("tags", [])))
        pub_categories = set(pub.get("categories", []))
        pub_keyword = pub.get("keyword", "").lower()

        score = 0.0

        # Tag overlap (strongest signal)
        tag_overlap = len(current_tags & pub_tags)
        score += tag_overlap * 3.0

        # Category match
        if current_categories & pub_categories:
            score += 2.0

        # Keyword word overlap
        current_words = set(current_keyword.split())
        pub_words = set(pub_keyword.split())
        word_overlap = len(current_words & pub_words)
        score += word_overlap * 1.5

        if score > 0:
            scored.append((score, pub))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [pub for _, pub in scored[:MAX_RELATED_LINKS]]


def insert_internal_links(article: dict, config: dict) -> dict:
    """Insert a 'Related Articles' section into the article body.

    Reads published.json to find existing articles, scores relevance,
    and appends a related articles section before any affiliate section.
    """
    published_articles = _load_published_articles()
    if not published_articles:
        return article

    related = find_related_articles(article, published_articles)
    if not related:
        logger.info("No related articles found for '%s'", article.get("keyword"))
        return article

    lang = article.get("lang", "en")
    base_url = config.get("site", {}).get("base_url", "/").rstrip("/")
    section = _build_related_section(related, lang, base_url)

    body = article["body"]

    # Insert before the affiliate section (marked by trailing ---) if present
    affiliate_marker = "\n---\n\n## おすすめ商品" if lang == "ja" else "\n---\n\n## Recommended Products"
    if affiliate_marker in body:
        body = body.replace(affiliate_marker, "\n\n" + section + affiliate_marker, 1)
    else:
        body = body + "\n\n" + section

    article["body"] = body
    logger.info(
        "Inserted %d internal links for '%s'",
        len(related),
        article.get("keyword"),
    )
    return article


def update_existing_articles(new_article: dict, config: dict) -> int:
    """Add a link to the new article in related existing articles.

    Returns the number of existing articles updated.
    """
    published_articles = _load_published_articles()
    if not published_articles:
        return 0

    lang = new_article.get("lang", "en")
    base_url = config.get("site", {}).get("base_url", "/").rstrip("/")
    new_slug = new_article.get("slug", "")
    new_title = new_article.get("front_matter", {}).get("title", "")

    if not new_slug or not new_title:
        return 0

    new_url = f"{base_url}/{lang}/{new_slug}/"
    updated_count = 0

    for pub in published_articles:
        if pub.get("lang") != lang:
            continue

        filepath = Path(pub.get("file_path", ""))
        if not filepath.exists():
            continue

        content = filepath.read_text(encoding="utf-8")

        # Skip if this article already links to the new one
        if new_slug in content:
            continue

        # Check if the published article is related
        # Build a fake article dict for relevance scoring
        fake_article = {
            "lang": pub.get("lang"),
            "keyword": pub.get("keyword"),
            "front_matter": {
                "tags": pub.get("tags", []),
                "categories": pub.get("categories", []),
            },
        }
        related = find_related_articles(fake_article, [
            {
                "lang": new_article.get("lang"),
                "keyword": new_article.get("keyword"),
                "tags": new_article.get("front_matter", {}).get("tags", []),
                "categories": new_article.get("front_matter", {}).get("categories", []),
            }
        ])

        if not related:
            continue

        # Append a link to the related articles section if it exists, otherwise add one
        if lang == "ja":
            related_header = "## 関連記事"
            link_line = f"- [{new_title}]({new_url})"
        else:
            related_header = "## Related Articles"
            link_line = f"- [{new_title}]({new_url})"

        if related_header in content:
            # Add to existing section (before the next section or end)
            content = _append_to_related_section(content, related_header, link_line)
        else:
            # Add new section before affiliate section or at the end
            affiliate_marker = (
                "\n---\n\n## おすすめ商品" if lang == "ja" else "\n---\n\n## Recommended Products"
            )
            new_section = f"\n\n{related_header}\n\n{link_line}\n"
            if affiliate_marker in content:
                content = content.replace(affiliate_marker, new_section + affiliate_marker, 1)
            else:
                content = content.rstrip() + new_section

        filepath.write_text(content, encoding="utf-8")
        updated_count += 1
        logger.info("Added internal link to existing article: %s", filepath.name)

    return updated_count


def _build_related_section(
    related: list[dict], lang: str, base_url: str
) -> str:
    """Build the related articles Markdown section."""
    if lang == "ja":
        header = "## 関連記事"
    else:
        header = "## Related Articles"

    lines = [header, ""]
    for pub in related:
        slug = pub.get("slug", "")
        title = pub.get("title", slug)
        url = f"{base_url}/{lang}/{slug}/"
        lines.append(f"- [{title}]({url})")

    return "\n".join(lines)


def _append_to_related_section(
    content: str, header: str, link_line: str
) -> str:
    """Append a link to an existing related articles section."""
    # Find the section and add before the next ## heading or end
    pattern = rf"({re.escape(header)}\n\n(?:- .+\n)*)"
    match = re.search(pattern, content)
    if match:
        existing_section = match.group(1)
        # Check we're not adding a duplicate
        if link_line.split("(")[1] not in existing_section:
            updated_section = existing_section.rstrip("\n") + "\n" + link_line + "\n"
            content = content.replace(existing_section, updated_section, 1)
    return content


def _load_published_articles() -> list[dict]:
    """Load published articles from published.json."""
    published_path = get_data_path("published.json")
    try:
        with open(published_path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("articles", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _normalize_tags(tags: list) -> list[str]:
    """Normalize tags to lowercase strings."""
    if not tags:
        return []
    return [str(t).lower().strip() for t in tags]
