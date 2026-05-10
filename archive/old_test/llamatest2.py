import autogen_config
from autogen import AssistantAgent

agent = AssistantAgent(
    name="test",
    system_message="あなたはテスト用アシスタントです。",
    llm_config={
        "model": autogen_config.llm_config["model"],
        "api_base": autogen_config.llm_config["api_base"],
        "api_type": "ollama",
        "client": "ollama",   # ← これが決定打
        "temperature": 0.2,
    }
)

result = agent.run("こんにちは。短く自己紹介して。")
print("RESULT:", result.summary)