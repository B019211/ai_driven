import json
import time
import urllib.request


OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen3:4b-instruct-2507-q4_K_M"


payload = {
    "model": MODEL_NAME,
    "messages": [
        {
            "role": "user",
            "content": "Write only: HELLO"
        }
    ],
    "stream": False,
    "think": False,
    "options": {
        "num_predict": 64
    }
}


body = json.dumps(payload).encode("utf-8")

request = urllib.request.Request(
    OLLAMA_URL,
    data=body,
    headers={
        "Content-Type": "application/json"
    },
    method="POST"
)


print("=== OLLAMA NATIVE API TEST ===")
print("URL   =", OLLAMA_URL)
print("MODEL =", MODEL_NAME)
print("THINK = False")

start = time.time()

with urllib.request.urlopen(request, timeout=120) as response:
    response_body = response.read().decode("utf-8")

elapsed = time.time() - start

data = json.loads(response_body)

print(f"\nOllama returned ({elapsed:.1f}s)")
print("\n=== RAW RESPONSE ===")
print(json.dumps(data, ensure_ascii=False, indent=2))

message = data.get("message", {})

print("\n=== CONTENT ===")
print(message.get("content"))

print("\n=== THINKING ===")
print(message.get("thinking"))

print("\n=== DONE ===")
print(data.get("done"))

print("\n=== EVAL COUNT ===")
print(data.get("eval_count"))