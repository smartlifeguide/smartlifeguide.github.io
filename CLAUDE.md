# Project Guidelines

## プロジェクト概要
AI (Gemini API) を活用した完全自動SEOブログ記事生成・公開・収益化システム。
GitHub Actions で毎日自動実行し、Hugo + GitHub Pages で日英バイリンガルブログを運営する。
月額コスト0円で不労所得を目指す。

## ターゲットペルソナ
- **メイン**: 40〜50代の主婦・パート勤務の女性 (例: 45歳、パート勤務の母親)
- **行動**: Google検索で「○○ おすすめ」「○○ 比較」と調べる層。SNSやAIチャットではなくブログ記事を参考にする
- **関心**: 家電選び、節約術、健康ケア、教育費、シニア親の見守り

## ニッチカテゴリ (ペルソナ最適化済み)
1. 家電・生活家電 (ロボット掃除機、食洗機、空気清浄機、ドラム式洗濯機)
2. 節約・家計管理 (電気代節約、食費節約、格安SIM、家計簿)
3. 健康・体のケア (肩こり、目の疲れ、腰痛マットレス、睡眠改善)
4. 教育費・子育てマネー (教育費、学資保険、タブレット学習、塾選び)
5. 見守り・シニアケア (見守りサービス、シニアスマホ、介護保険、見守りカメラ)

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
- [x] Step 16: GitHub デプロイ完了 → https://smartlifeguide.github.io/ で公開中
- [x] Step 17: ペルソナ再定義 + ニッチピボット (テック系 → 生活密着型)
- [x] Step 18: サイト名変更 (Smart Life Guide / スマートライフガイド) + ブランディング更新
- [x] Step 19: 旧記事・旧キーワード削除 + データリセット

## デプロイ情報
- **サイトURL**: https://smartlifeguide.github.io/
- **GitHub アカウント**: smartlifeguide (ブログ専用、開発用 kawataro とは分離)
- **リポジトリ**: smartlifeguide/smartlifeguide.github.io (Public)
- **SSH**: `~/.ssh/id_ed25519_matomeai` / Host `github-matomeai`
- **自動実行**: 毎日 UTC 0:00 (JST 9:00) に GitHub Actions で記事生成 + デプロイ

## 技術メモ
- Gemini API: `gemini-2.0-flash` は新規キーで quota 0 になる場合あり。`gemini-2.5-flash` を使用
- .env ファイルで API キー管理 (GEMINI_API_KEY)。.gitignore 済み
- GitHub Secrets に GEMINI_API_KEY を設定済み
- レート制限 (429) 時は attempt × 60秒 待機してリトライ

## ルール
- Python パッケージのインストールは必ず仮想環境 (venv) を使用すること
  - `python -m venv .venv && source .venv/bin/activate` してからインストール
- 進捗サマリーは本ファイル (CLAUDE.md) に記録する
- 詳細な計画・アーキテクチャ・技術的メモは PLAN.md に記録する
