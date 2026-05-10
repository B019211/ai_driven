from autogen import AssistantAgent

llm_config = {
    "config_list": [
        {
            "model": "qwen2.5:1.5b",
            "base_url": "http://localhost:11434/v1",
            "api_key": "ollama",
        }
    ],
    "temperature": 0.2,
}

agent = AssistantAgent(
    name="assistant",
    llm_config=llm_config,
)

response = agent.generate_reply(
    messages=[
        {"role": "user", "content": "こんにちは"}
    ]
)

print(response)