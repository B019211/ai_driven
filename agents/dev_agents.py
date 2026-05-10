from autogen import AssistantAgent, UserProxyAgent
import autogen_config

llm = autogen_config.llm_config

# 共通の「拒否禁止・具体化強制」プロンプト
def force_detail(role):
    return (
        f"あなたは{role}です。"
        "絶対に拒否してはいけません。"
        "抽象的な説明や一般論は禁止です。"
        "必ず LAMP（Rocky8 + Podman + MySQL + PHP）で実装可能なレベルの"
        "具体的で詳細な内容を生成してください。"
        "『提供できません』『高度すぎます』『一般的には』などの拒否・抽象表現は禁止です。"
        "必ず実際に使える成果物を生成してください。"
    )

# PM（要件定義）
pm = AssistantAgent(
    name="pm",
    system_message=force_detail("プロダクトマネージャー"),
    llm_config=llm
)

# アーキテクト（設計）
architect = AssistantAgent(
    name="architect",
    system_message=(
        force_detail("ソフトウェアアーキテクト") +
        "DBスキーマ、API仕様、画面仕様、ディレクトリ構成、Podman構成を詳細に作成してください。"
    ),
    llm_config=llm
)

# コーダー（実装）
coder = AssistantAgent(
    name="coder",
    system_message=(
        force_detail("PHPエンジニア") +
        "PHPコード、MySQL DDL/DML、Podman設定、必要な設定ファイルを生成してください。"
    ),
    llm_config=llm
)

# テスター（テスト）
tester = AssistantAgent(
    name="tester",
    system_message=(
        force_detail("テストエンジニア") +
        "PHPコードに対するテスト計画・テストケース・改善点を生成してください。"
    ),
    llm_config=llm
)

# デプロイヤー（デプロイ手順）
deployer = AssistantAgent(
    name="deployer",
    system_message=(
        force_detail("DevOpsエンジニア") +
        "アプリ配置先は /home/vboxuser/containers/html/ です。"
        "Podman 再起動手順、MySQL 初期データ投入手順、VSCode Remote-SSH での配置手順を生成してください。"
        "実際のSSH接続やPodman実行は行わず、手順とファイル内容のみを生成してください。"
    ),
    llm_config=llm
)

# UserProxyAgent（ループ防止・Docker無効化）
user = UserProxyAgent(
    name="user",
    human_input_mode="NEVER",
    code_execution_config={"use_docker": False},
    max_consecutive_auto_reply=1
)
