import os
from google import genai
from config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)
for m in client.models.list():
    if getattr(m, "supported_actions", None):
        print(f"Name: {m.name}, Methods: {m.supported_actions}")
    elif hasattr(m, "supported_generation_methods"):
        print(f"Name: {m.name}, Methods: {m.supported_generation_methods}")
    else:
        print(f"Name: {m.name}, Attributes: {list(m.__dict__.keys())}")
