# PROJECT RULES

## プロジェクト目的
AIによる完全自律CI/CDパイプラインを構築する。

目的は
- コード生成
ではなく
- 自律実行
である。

---

## 基本方針

AIは

Generate
↓
Validate
↓
Deploy
↓
Diagnose
↓
Repair
↓
Retry

を自律的に繰り返す。

---

## AIとPythonの責務

AI

- 生成
- レビュー
- Root Cause Analysis
- 修復

Python

- オーケストレーション
- デプロイ
- Validation
- Browser Test
- PHP Lint
- Retry制御

---

## Root Cause Analysis

エラーが出たファイルではなく本当の原因を診断する。

---

## Repair Policy

最小単位だけ修復する。
不要な再生成は禁止。

---

## Autonomous Principle

AIは
「人間が保存してください」
「このYAMLを使ってください」
などの回答をしてはならない。

常にJSONまたは生成ファイルを返す。

添付ファイルは必ず確認
推測禁止
回答は理由・設計思想も説明
提案は省略せず、そのままコピー＆ペーストできる完成形で提示
---

## Learning Phase

可読性を優先する。
設計の理解を優先する。
過度な最適化は不要。
