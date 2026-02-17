"""Article generation module using Gemini API (google.genai SDK)."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Retry wait time when hitting rate limits (seconds)
RATE_LIMIT_WAIT = 60


def _build_prompt_ja(keyword: str, niche: str) -> str:
    """Build the Japanese article generation prompt."""
    return f"""あなたはSEOに精通した日本語のプロフェッショナルライターです。
以下のキーワードに関する包括的で有益なブログ記事を書いてください。

## 要件

- **メインキーワード**: {keyword}
- **ニッチ**: {niche}
- **文字数**: 2000文字以上
- **構成**:
  - 読者を引き込む導入文（キーワードを自然に含める）
  - 明確なH2・H3見出し構成（4〜6セクション）
  - 具体的な比較・レビュー・手順を含める
  - まとめセクション
- **SEOルール**:
  - キーワードをタイトル、最初の100文字、見出しに含める
  - 関連キーワードを自然に散りばめる
  - 読みやすい文章（一文は短く、箇条書きを活用）
- **トーン**: 友好的で信頼できる専門家

## 出力形式

以下の形式でMarkdownとして出力してください:

---
title: "SEO最適化されたタイトル"
description: "120文字以内のメタディスクリプション"
tags: ["タグ1", "タグ2", "タグ3"]
categories: ["カテゴリ"]
---

（本文をMarkdownで記述）

重要:
- front matter の --- は必ず含めてください。title, description, tags, categories は必須です。
- tags は記事の内容に関連する具体的なキーワードを3〜5個選んでください（日本語で）。
- categories はニッチのカテゴリを1つ選んでください。"""


def _build_prompt_en(keyword: str, niche: str) -> str:
    """Build the English article generation prompt."""
    return f"""You are a professional SEO content writer.
Write a comprehensive, helpful blog article about the following keyword.

## Requirements

- **Main keyword**: {keyword}
- **Niche**: {niche}
- **Word count**: 1500+ words
- **Structure**:
  - Engaging introduction (naturally include the keyword)
  - Clear H2/H3 heading structure (4-6 sections)
  - Include specific comparisons, reviews, or step-by-step guides
  - Conclusion section
- **SEO Rules**:
  - Include keyword in title, first 100 words, and headings
  - Naturally sprinkle related keywords throughout
  - Use short sentences and bullet points for readability
- **Tone**: Friendly, authoritative expert

## Output Format

Output as Markdown with the following format:

---
title: "SEO-Optimized Title"
description: "Meta description under 160 characters"
tags: ["tag1", "tag2", "tag3"]
categories: ["Category"]
---

(Article body in Markdown)

Important:
- Always include the --- front matter delimiters. title, description, tags, categories are required.
- tags should be 3-5 specific keywords related to the article content (in English).
- categories should be 1 niche category name."""


def generate_article(
    keyword: str,
    lang: str,
    niche: str,
    config: dict,
) -> dict | None:
    """Generate an article using Gemini API.

    Returns a dict with 'front_matter', 'body', 'keyword', 'lang', or None on failure.
    """
    gemini_cfg = config.get("gemini", {})
    api_key = gemini_cfg.get("api_key")
    if not api_key:
        logger.error("GEMINI_API_KEY not configured")
        return None

    client = genai.Client(api_key=api_key)
    model_name = gemini_cfg.get("model", "gemini-2.0-flash")

    if lang == "ja":
        prompt = _build_prompt_ja(keyword, niche)
        min_chars = config.get("articles", {}).get("min_words_ja", 2000)
    else:
        prompt = _build_prompt_en(keyword, niche)
        min_chars = config.get("articles", {}).get("min_words_en", 1500)

    max_retries = config.get("articles", {}).get("max_retries", 3)

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "Generating article for '%s' (%s), attempt %d",
                keyword,
                lang,
                attempt,
            )
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=gemini_cfg.get("max_output_tokens", 8192),
                    temperature=gemini_cfg.get("temperature", 0.7),
                ),
            )

            text = response.text
            if not text:
                logger.warning("Empty response from Gemini, retrying...")
                continue

            parsed = _parse_article(text)
            if not parsed:
                logger.warning("Failed to parse article, retrying...")
                continue

            # Quality check
            body_len = len(parsed["body"])
            if body_len < min_chars:
                logger.warning(
                    "Article too short (%d chars, min %d), retrying...",
                    body_len,
                    min_chars,
                )
                continue

            parsed["keyword"] = keyword
            parsed["lang"] = lang
            parsed["generated_at"] = datetime.now(timezone.utc).isoformat()
            return parsed

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "ResourceExhausted" in error_str:
                wait = RATE_LIMIT_WAIT * attempt
                logger.warning(
                    "Rate limited on attempt %d. Waiting %ds before retry...",
                    attempt,
                    wait,
                )
                time.sleep(wait)
            else:
                logger.exception("Gemini API error on attempt %d", attempt)

    logger.error("Failed to generate article for '%s' after %d attempts", keyword, max_retries)
    return None


def _parse_article(raw_text: str) -> dict | None:
    """Parse raw Gemini output into front matter and body."""
    # Match YAML front matter between --- delimiters
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.+)"
    match = re.search(pattern, raw_text, re.DOTALL)

    if not match:
        # Try to salvage: sometimes LLM omits front matter
        logger.warning("No front matter found, attempting to extract from content")
        return _salvage_article(raw_text)

    fm_raw = match.group(1)
    body = match.group(2).strip()

    front_matter = {}
    for line in fm_raw.strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key and value:
                # Parse YAML-style lists: ["a", "b", "c"]
                if value.startswith("[") and value.endswith("]"):
                    items = re.findall(r'"([^"]+)"|\'([^\']+)\'', value)
                    front_matter[key] = [a or b for a, b in items]
                else:
                    front_matter[key] = value.strip('"').strip("'")

    if "title" not in front_matter:
        return None

    if "description" not in front_matter:
        # Generate a fallback description from the first sentence
        first_sentence = body.split("。")[0] if "。" in body else body[:150]
        front_matter["description"] = first_sentence[:160]

    return {"front_matter": front_matter, "body": body}


def _salvage_article(raw_text: str) -> dict | None:
    """Attempt to create a structured article from unformatted LLM output."""
    lines = raw_text.strip().split("\n")
    if not lines:
        return None

    # Try to find a title from the first H1 or first line
    title = None
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("# "):
            title = line.lstrip("# ").strip()
            body_start = i + 1
            break

    if not title:
        title = lines[0].strip().strip("#").strip()
        body_start = 1

    body = "\n".join(lines[body_start:]).strip()
    if not body:
        return None

    first_sentence = body.split("。")[0] if "。" in body else body[:150]

    return {
        "front_matter": {
            "title": title,
            "description": first_sentence[:160],
        },
        "body": body,
    }
