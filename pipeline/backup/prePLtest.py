from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)

print("before")

response = client.chat.completions.create(
    model="qwen3:8b",
    messages=[
        {"role": "user", "content": "こんにちは"}
    ],
    temperature=0
)

print("after")
print(response.choices[0].message.content)
