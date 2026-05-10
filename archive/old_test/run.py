from agents.dev_agents import user, pm, architect, coder, tester, deployer

# スタート：PM に要件を伝える
result = user.initiate_chat(
    pm,
    message="LAMP構成（Rocky8 + Podman + MySQL + PHP）でミニSNSを作りたい。ユーザー登録、投稿、フォロー、タイムラインが欲しい。"
)

# PM → アーキテクト
result = pm.initiate_chat(architect, message=result.summary, max_turns=1)

# アーキテクト → コーダー
result = architect.initiate_chat(coder, message=result.summary, max_turns=1)

# コーダー → テスター
result = coder.initiate_chat(tester, message=result.summary, max_turns=1)

# テスター → コーダー（バグ修正ループ）
result = tester.initiate_chat(coder, message=result.summary, max_turns=1)

# コーダー → デプロイヤー
result = coder.initiate_chat(deployer, message=result.summary, max_turns=1)

print(result.summary)
