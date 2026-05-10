import logging
from litellm import completion

logging.basicConfig(
    filename="ai_run.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

def log_print(msg):
    print(msg)
    logging.info(msg)


def ask(role, message):
    log_print(f"\n=== {role} ===")
    log_print(f"INPUT: {message}")

    try:
        res = completion(
            model="gemini/gemini-2.5-flash",
            messages=[
                {"role": "system", "content": f"あなたは{role}です。"},
                {"role": "user", "content": message}
            ]
        )

        output = res["choices"][0]["message"]["content"]
        log_print(f"OUTPUT: {output}")
        return output

    except Exception as e:
        log_print(f"ERROR: {str(e)}")
        raise


if __name__ == "__main__":

    context = """
LAMP構成（Rocky Linux 8 + Podman + MySQL + PHP）でミニSNSを作る。

すでにAnsibleで以下が構築済み：
- Podman pod (lamp-pod)
- MySQLコンテナ
- PHP Webコンテナ
- /home/vboxuser/containers/html がWebルート
- 8080で公開済み

機能：
- ユーザー登録・ログイン
- 投稿
- フォロー
- タイムライン
"""

    pm = ask("プロダクトマネージャー", context)

    arch = ask("システムアーキテクト", pm)

    code = ask("PHPエンジニア", arch)

    test = ask("テスター", code)

    deploy = ask(
        "デプロイエンジニア（Ansible連携）",
        f"""
以下のコードを既存環境へデプロイする手順を作成してください。

条件：
- Ansibleでサーバ構築済み
- Podman pod: lamp-pod 稼働中
- Webディレクトリ: /home/vboxuser/containers/html
- PHPコンテナはwebという名前

やること：
- ファイル配置手順
- 必要なディレクトリ
- コンテナ再起動手順
- 初期化SQLがあれば適用方法

コード：
{code}
"""
    )

    review = ask("シニアアーキテクト", deploy)

    log_print("\n=== FINAL OUTPUT ===")
    log_print(review)