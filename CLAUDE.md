# Project Guidelines

## プロジェクト概要
AI (Gemini API) を活用した完全自動SEOブログ記事生成・公開・収益化システム。
GitHub Actions で毎日自動実行し、Hugo + GitHub Pages で日英バイリンガルブログを運営する。
月額コスト0円で不労所得を目指す。

## 進捗サマリー
- [x] Step 1: プロジェクト基盤 (pyproject.toml, requirements.txt, config.yaml, .gitignore)
- [x] Step 2: 設定モジュール + データファイル (pipeline/config.py, data/*.json)
- [x] Step 3: キーワード調査モジュール (pipeline/keyword_researcher.py)
- [x] Step 4: 記事生成モジュール (pipeline/article_generator.py)
- [x] Step 5: アフィリエイトリンクモジュール (pipeline/affiliate_linker.py)
- [x] Step 6: 公開モジュール (pipeline/publisher.py)
- [x] Step 7: メインパイプライン (pipeline/main.py)
- [x] Step 8: Hugo サイト構築 (site/, テーマ, 多言語対応, AdSense)
- [x] Step 9: GitHub Actions ワークフロー (.github/workflows/generate.yml)
- [x] Step 10: 依存パッケージインストール & 動作確認 (Python deps OK, Hugo build OK)
- [x] Step 11: 自動タグ付与 (article_generator.py プロンプト改修 + publisher.py front matter 対応)
- [x] Step 12: 内部リンクモジュール (pipeline/internal_linker.py — 関連記事検出・双方向リンク挿入)
- [x] Step 13: パイプライン統合 (main.py に内部リンクステップ追加)
- [x] Step 14: SDK移行 (google.generativeai → google.genai) + レート制限対応
- [x] Step 15: 初回テスト実行成功 (JA: スマート照明 24KB, EN: productivity apps 20KB)

## 技術メモ
- Gemini API: `gemini-2.0-flash` は新規キーで quota 0 になる場合あり。`gemini-2.5-flash` を使用
- .env ファイルで API キー管理 (GEMINI_API_KEY)。.gitignore 済み
- レート制限 (429) 時は attempt × 60秒 待機してリトライ

## ルール
- Python パッケージのインストールは必ず仮想環境 (venv) を使用すること
  - `python -m venv .venv && source .venv/bin/activate` してからインストール
- 進捗サマリーは本ファイル (CLAUDE.md) に記録する
- 詳細な計画・アーキテクチャ・技術的メモは PLAN.md に記録する
