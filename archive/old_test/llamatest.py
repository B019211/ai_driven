from autogen import AssistantAgent
import autogen_config

agent = AssistantAgent(
    name="test",
    system_message="あなたはテスト用アシスタントです。",
    llm_config=autogen_config.llm_config
)

reply = agent.generate_reply(
    messages=[{"role": "user", "content": "こんにちは。短く自己紹介して。"}]
)

print(reply)
