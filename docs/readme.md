# AI Driven CI/CD Pipeline

## 概要

本プロジェクトは、AIによる自律的なCI/CDパイプラインの構築を目的としています。

AIが生成した成果物をPythonパイプラインが検証・デプロイし、
ブラウザ検証やPHP構文チェックなどの実行結果を基に、
AIがRoot Cause Analysisを行い、
必要最小限の修復を自動実施することを目標としています。

最終目標は

Generate
→ Validate
→ Deploy
→ Browser Test
→ Root Cause Analysis
→ Repair
→ Retry

を完全自動で実現することです。

---

## 主な機能

- AIによるAnsible生成
- AIによるPHP生成
- JSON出力
- Review Loop
- YAML Validation
- Remote Validation
- Browser Validation
- PHP Lint
- Root Cause Analysis
- Auto Repair
- Auto Retry

---

## ディレクトリ

```
pipeline/
context/
prompts/
generated/
logs/
```

---

## 詳細

AIが読むルールは

PROJECT_RULES.md

を参照してください。