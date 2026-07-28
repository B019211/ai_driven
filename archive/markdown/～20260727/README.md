# AI DevOps Pipeline

AIを利用して、

- インフラ構成生成
- Ansible生成
- Podman構成生成
- PHPアプリ生成
- セキュリティレビュー
- 自動修正（予定）

を行う AI駆動 DevOps パイプラインです。

---

# 概要

このプロジェクトは Gemini API を利用し、
AIによる Infrastructure as Code 自動生成を目的としています。

現在は以下を実装済みです。

- Architecture Context 読み込み
- Rule Context 読み込み
- Gemini による JSON生成
- 生成結果の JSON parse
- ファイル自動生成
- Reviewer AI によるセキュリティレビュー
- Review Result 出力

---

# 現在の構成

```text
context/
 ├ architecture.md
 ├ system_rules.md
 ├ reviewer_rules.md
 └ output_format.md

pipeline/
 └ ai_pipeline.py

generated/
 ├ runtime/
 ├ files/
 └ reports/

logs/
```
