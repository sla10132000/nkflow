# CLAUDE.md — Monorepo Root

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Agent behavior policy is defined in `.claude/CLAUDE.md` — read it first.

---

## Repository Structure

This is a monorepo containing multiple products sharing a common data pipeline.

| Directory | Description |
|-----------|-------------|
| `nkflow/` | 日経225 投資分析基盤 — 詳細は `nkflow/CLAUDE.md` |
| `datalake/` | 共有データパイプライン (バッチ処理・分析・シグナル生成) |

## Commands

### Makefile (推奨: 全コマンドはここから実行)

```bash
make help            # 利用可能なコマンド一覧
make deploy          # CDK + frontend を両方デプロイ (通常はこれ)
make deploy-cdk      # CDK のみ (backend/Lambda/インフラ変更時)
make deploy-frontend # Vue frontend のみビルド&S3同期
make pull            # S3 → stocks.db ダウンロード (worktree 対応)
make push-db         # stocks.db → S3 アップロード (worktree 対応)
make test            # backend + datalake pytest
make test-datalake   # datalake pytest のみ
make test-frontend   # vitest
make lint            # ruff
```

## Product-Specific Documentation

- **nkflow**: See `nkflow/CLAUDE.md` for architecture, ER diagram, screen design, API reference
- **datalake**: See `datalake/` for data pipeline code (shared across products)
