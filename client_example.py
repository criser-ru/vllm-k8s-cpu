import os
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key=os.environ["VLLM_API_KEY"])
resp = client.chat.completions.create(
    model="qwen2.5-0.5b-instruct",
    messages=[{"role": "user", "content": "Привет! Кто ты?"}],
    max_tokens=50,
)
print(resp.choices[0].message.content)