# 自動ブログ収益化システム - 詳細計画

## アーキテクチャ

```
GitHub Actions (毎日自動実行)
    │
    ▼
Python パイプライン
    ├── 1. キーワード調査 (pytrends + Google Suggest)
    ├── 2. 記事生成 (Gemini API 無料枠)
    ├── 3. SEO最適化 + アフィリエイトリンク挿入
    └── 4. Hugo サイトに自動公開 (GitHub Pages)
         │
         ▼
    静的サイト (Hugo + GitHub Pages)
    ├── 日本語記事 (/ja/)
    ├── 英語記事 (/en/)
    ├── Google AdSense 広告
    └── アフィリエイトリンク
```

## 技術スタック

| コンポーネント | 技術 | コスト |
|---|---|---|
| LLM | Gemini API (無料枠: 1500 RPD) | 無料 |
| 静的サイト生成 | Hugo (多言語対応) | 無料 |
| ホスティング | GitHub Pages | 無料 |
| CI/CD | GitHub Actions (cron) | 無料 |
| キーワード調査 | pytrends + Google Suggest API | 無料 |
| 収益化 | Google AdSense + Amazon Associates | 無料 |

## ファイル構成

```
passive_income_002/
├── .github/workflows/generate.yml   # 毎日の自動実行ワークフロー
├── pipeline/
│   ├── __init__.py
│   ├── config.py                    # 設定管理 (YAML読込 + 環境変数上書き)
│   ├── keyword_researcher.py        # pytrends + Google Suggest でキーワード調査
│   ├── article_generator.py         # Gemini API で記事生成 (日英対応)
│   ├── affiliate_linker.py          # Amazon Associates リンク自動挿入
│   ├── publisher.py                 # Hugo content配置 + git操作
│   └── main.py                      # パイプライン統合 (CLI エントリポイント)
├── site/                            # Hugo サイト
│   ├── hugo.toml                    # Hugo設定 (多言語・SEO・AdSense)
│   ├── content/{en,ja}/             # 自動生成記事
│   └── themes/minimal-seo/         # カスタムテーマ (OGP, 構造化データ, 広告枠)
├── data/
│   ├── keywords.json                # キーワードリスト (スコア付き)
│   ├── published.json               # 公開済み記事追跡 (重複防止)
│   └── niches.json                  # ニッチ定義 + シードキーワード
├── config.yaml                      # グローバル設定
├── pyproject.toml
├── requirements.txt
├── CLAUDE.md                        # プロジェクトルール + 進捗サマリー
└── PLAN.md                          # 本ファイル (詳細計画)
```

## 各モジュール詳細

### pipeline/config.py
- `load_config()`: config.yaml を読み込み、環境変数 (GEMINI_API_KEY, AMAZON_TAG_*) で上書き
- `get_data_path()`, `get_content_dir()`: パスヘルパー

### pipeline/keyword_researcher.py
- `fetch_google_suggestions()`: Google Suggest API でオートコンプリート候補取得
- `fetch_trends_interest()`: pytrends で検索トレンドスコア取得 (5件ずつバッチ処理)
- `score_keywords()`: 検索ボリューム × ロングテールボーナスでスコアリング
- `expand_keywords_from_niches()`: ニッチのシードキーワードから候補拡張
- `research_keywords()`: 全言語の調査を統合実行、data/keywords.json に保存
- `get_unused_keyword()`: 未使用の最高スコアキーワードを取得

### pipeline/article_generator.py
- `generate_article()`: Gemini API で記事生成 (リトライ付き、品質チェック)
- プロンプト: SEO最適化された構成 (H2/H3見出し、メタディスクリプション、tags、categories)
- 出力: YAML front matter (title, description, tags, categories) + Markdown 本文
- 品質チェック: 最低文字数 (JA: 2000字, EN: 1500字)
- tags: LLM が記事内容から3〜5個の関連タグを自動生成
- categories: ニッチカテゴリを1つ自動選択

### pipeline/affiliate_linker.py
- 記事本文からプロダクトカテゴリを正規表現で検出
- Amazon 検索URLを生成し、おすすめ商品セクションを追加
- JA → amazon.co.jp, EN → amazon.com

### pipeline/internal_linker.py (NEW)
- `find_related_articles()`: タグ重複・カテゴリ一致・キーワード類似度でスコアリング → 最大3件の関連記事を選出
- `insert_internal_links()`: 新規記事に「関連記事」セクションを挿入（アフィリエイトセクションの前に配置）
- `update_existing_articles()`: 既存記事にも新記事へのリンクを双方向で追加
- スコアリング: タグ重複×3 + カテゴリ一致×2 + キーワード単語重複×1.5

### pipeline/publisher.py
- `publish_article()`: Hugo content ディレクトリに Markdown ファイル配置 (tags, categories を front matter に含む)
- `_record_published()`: data/published.json に記録 (tags, categories 含む、重複防止)
- `git_commit_and_push()`: 自動コミット & プッシュ
- `keyword_to_slug()`: キーワード → URL スラグ変換

### pipeline/main.py
- `run_pipeline()`: 全ステップを順次実行
  1. キーワード調査
  2. 言語ごとに未使用キーワードを選択
  3. Gemini API で記事生成
  4. 内部リンク挿入 (関連記事セクション)
  5. アフィリエイトリンク挿入
  6. Hugo content に配置 + 記録
  7. 既存記事に新記事への内部リンクを追加 (双方向)
  8. git commit & push
- CLI: `python -m pipeline.main [--skip-research] [--skip-git]`

## GitHub Actions ワークフロー
- トリガー: 毎日 UTC 0:00 (cron) + 手動 (workflow_dispatch)
- ジョブ1 (generate): Python パイプライン実行 → 記事生成 → git commit & push
- ジョブ2 (deploy): Hugo ビルド → GitHub Pages デプロイ
- シークレット: GEMINI_API_KEY, AMAZON_TAG_JA, AMAZON_TAG_EN

## 収益化ロードマップ
1. Week 1: システム構築・初期記事30本生成
2. Week 2-4: 毎日2本ずつ自動投稿 (日英各1本)
3. Month 2: Google Search Console 登録、インデックス確認
4. Month 3: 100記事到達 → Google AdSense 申請
5. Month 4-6: SEO効果→オーガニック流入増加
6. Month 6+: 安定収益化

## 残タスク
- [x] 依存パッケージインストール & 動作確認
- [x] Hugo ローカルビルド確認
- [x] 自動タグ付与 (tags, categories)
- [x] 内部リンクモジュール (双方向関連記事リンク)
- [ ] Gemini API キー設定 & テスト実行
- [ ] GitHub リポジトリ設定 (Secrets, Pages 有効化)
- [ ] 初期記事バッチ生成
