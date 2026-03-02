"""Article generation module using Gemini API (google.genai SDK)."""

from __future__ import annotations

import json
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
    current_year = datetime.now(timezone.utc).year
    return f"""あなたはSEOに精通した日本語のプロフェッショナルライターです。
以下のキーワードに関する包括的で有益なブログ記事を書いてください。

**重要: 現在は{current_year}年です。記事中の年号は必ず{current_year}年を使用してください。「{current_year}年版」「{current_year}年最新」のように書いてください。2024年や2025年など古い年号は絶対に使わないでください。**

## ターゲット読者
- 40〜50代の主婦・パート勤務の女性
- ITに詳しくなく、Google検索で情報を探す層
- わかりやすく、やさしい言葉で書いてください

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
- **トーン**: 友好的で信頼できる、近所のお姉さんのようなやさしい口調

## 装飾ボックス
記事中で以下のHTMLボックスを適切な箇所に使ってください（合計2〜4個）:

ポイントや要点を伝える時:
<div class="point-box">
<p>ここに重要なポイントを書く</p>
</div>

注意点を伝える時:
<div class="warning-box">
<p>ここに注意点を書く</p>
</div>

補足情報やメモ:
<div class="memo-box">
<p>ここに補足情報を書く</p>
</div>

また、比較記事の場合は必ずMarkdownの表（テーブル）を使って比較してください。

## 要件（必ず守ること）
- 記事内では必ず実在する具体的な商品名・型番を3つ以上紹介してください（例: パナソニック NA-LX129C、日立 BD-STX130J など）。
- A社・B社のような架空名は絶対に使わないでください。

## 出力形式

以下の形式でMarkdownとして出力してください:

---
title: "SEO最適化されたタイトル"
description: "120文字以内のメタディスクリプション"
tags: ["タグ1", "タグ2", "タグ3"]
categories: ["カテゴリ"]
---

（本文をMarkdownで記述）

```json
{{"products": ["実在する商品名1", "実在する商品名2", "実在する商品名3"]}}
```

重要:
- front matter の --- は必ず含めてください。title, description, tags, categories は必須です。
- tags は記事の内容に関連する具体的なキーワードを3〜5個選んでください（日本語で）。
- categories はニッチのカテゴリを1つ選んでください。
- **記事本文の最後に必ず上記の```json```ブロックを出力してください。** 記事中で紹介した実在する商品名を3つ記載してください。このJSONブロックがないと記事は不完全として拒否されます。"""


def _build_prompt_en(keyword: str, niche: str) -> str:
    """Build the English article generation prompt."""
    current_year = datetime.now(timezone.utc).year
    return f"""You are a professional SEO content writer.
Write a comprehensive, helpful blog article about the following keyword.

**IMPORTANT: The current year is {current_year}. Always use {current_year} when referencing the current year in the article (e.g. "Best ... in {current_year}", "{current_year} Guide"). Never use 2024 or 2025.**

## Target Reader
- Families looking for practical advice on household topics
- Clear, easy-to-read language for general audience

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
- **IMPORTANT**: You MUST mention at least 3 real, specific product names with model numbers in the article (e.g. "iRobot Roomba j9+", "Dyson V15 Detect"). Never use fictional names like "Brand A" or "Product X".

## Decoration Boxes
Use these HTML boxes at appropriate points in the article (2-4 total):

For key points:
<div class="point-box en">
<p>Key point here</p>
</div>

For warnings or cautions:
<div class="warning-box en">
<p>Warning here</p>
</div>

For tips or notes:
<div class="memo-box en">
<p>Note here</p>
</div>

For comparison articles, always use Markdown tables.

## Output Format

Output as Markdown with the following format:

---
title: "SEO-Optimized Title"
description: "Meta description under 160 characters"
tags: ["tag1", "tag2", "tag3"]
categories: ["Category"]
---

(Article body in Markdown)

```json
{{"products": ["Real Product Name 1", "Real Product Name 2", "Real Product Name 3"]}}
```

Important:
- Always include the --- front matter delimiters. title, description, tags, categories are required.
- tags should be 3-5 specific keywords related to the article content (in English).
- categories should be 1 niche category name.
- **You MUST include the ```json``` block at the very end with 3 real product names from the article. The article will be rejected without this block.**"""


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
                    thinking_config=types.ThinkingConfig(thinking_budget=2048),
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

    # Clean up LLM artifacts
    body = _clean_body(body)

    # Extract product keywords JSON from end of body
    product_keywords = _extract_product_keywords(body)
    # Remove the JSON block from the article body
    body = _strip_product_json(body)

    result = {"front_matter": front_matter, "body": body}
    if product_keywords:
        result["product_keywords"] = product_keywords
    return result


def _clean_body(body: str) -> str:
    """Remove LLM-generated artifacts from article body."""
    # Remove broken image tags with example.com or placeholder URLs
    body = re.sub(r'!\[[^\]]*\]\(https?://(?:www\.)?example\.com[^)]*\)(?:\{[^}]*\})?', '', body)
    # Remove broken Kramdown-style image attributes: {: width="..." height="..."}
    body = re.sub(r'\{:\s*width="[^"]*"\s*height="[^"]*"\s*\}', '', body)
    # Remove placeholder image notes like ※画像はイメージです
    body = re.sub(r'※画像はイメージです。?', '', body)
    # Remove orphaned image alt text without URL: ![text]() or ![text]
    body = re.sub(r'!\[[^\]]*\]\(\s*\)', '', body)
    # Clean up multiple blank lines
    body = re.sub(r'\n{3,}', '\n\n', body)
    return body.strip()


def _extract_product_keywords(body: str) -> list[str]:
    """Extract product keywords from a JSON block at the end of the article body."""
    # Match ```json ... ``` block containing "products"
    pattern = r'```json\s*\n?\s*(\{[^`]*"products"[^`]*\})\s*\n?\s*```'
    match = re.search(pattern, body, re.DOTALL)
    if not match:
        return []

    try:
        data = json.loads(match.group(1))
        products = data.get("products", [])
        if isinstance(products, list):
            return [p for p in products if isinstance(p, str) and p.strip()]
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse product JSON block")
    return []


def _strip_product_json(body: str) -> str:
    """Remove the product JSON block from article body."""
    pattern = r'\s*```json\s*\n?\s*\{[^`]*"products"[^`]*\}\s*\n?\s*```\s*$'
    return re.sub(pattern, "", body, flags=re.DOTALL).rstrip()


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
