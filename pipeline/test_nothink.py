from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
    timeout=120,
    max_retries=0,
)

response = client.chat.completions.create(
    model="qwen3:4b-instruct-2507-q4_K_M",
    messages=[
        {
            "role": "user",
            "content": "Write only: HELLO",
        }
    ],
    temperature=0.0,
    max_tokens=64,
    extra_body={
        "num_predict": 64,
        "think": False,
    },
)

print(response)
print("CONTENT =", response.choices[0].message.content)
print("REASONING =", getattr(response.choices[0].message, "reasoning", None))