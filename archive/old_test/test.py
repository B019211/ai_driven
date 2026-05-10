import ollama

print("Calling Ollama...")
res = ollama.generate(model="qwen2.5:1.5b", prompt="こんにちは。短く自己紹介して。")
print(res)