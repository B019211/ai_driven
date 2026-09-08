# PROJECT

## プロジェクト目的

AIによる自律型CI/CDパイプラインを構築する。

本プロジェクトでは、AIによるコード生成だけを目的とせず、

Generate
↓
Validate
↓
Deploy
↓
Browser Validation
↓
Root Cause Analysis
↓
Repair
↓
Retry

という一連の開発・運用サイクルを自律化することを目標とする。

---

## 最終目標

以下を人間による手作業を最小限にして実行できるパイプラインを構築する。

1. AIによる成果物生成
2. 自動Validation
3. 自動Deploy
4. Browser Validation
5. エラー発生時のRoot Cause Analysis
6. 必要最小限のRepair
7. 自動Retry
8. 成功するまでの再検証

---

## 現在のフェーズ

Learning Phase

実装そのものだけでなく、

- AI駆動開発
- CI/CD設計
- 自動Validation
- Root Cause Analysis
- AIによる自動修復

について理解を深めることを重視する。

---

## 開発対象

主な開発対象はAI駆動CI/CDパイプラインである。

現在の主要実装対象：

pipeline/ai_pipeline.py

---

## 開発原則

生成されたアプリケーションを人間が直接修正して完成させることを前提としない。

問題が発生した場合は、

エラー
↓
原因分析
↓
修復方針
↓
AIによる修正
↓
再検証

というパイプライン側の仕組みによって解決することを目指す。
