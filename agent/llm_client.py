"""
Groq client wrapper.

Kept deliberately thin — a single function that sends messages + tools
and returns the model's response. If you ever swap providers (a hosted
fine-tuned model, a different API), this is the only file that changes.
"""

import os
from groq import Groq

# Reads GROQ_API_KEY from environment. Never hardcode the key in source.
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

MODEL_NAME = "openai/gpt-oss-120b"


def call_llm(messages: list, tools: list):
    """
    Sends the conversation + available tools to Groq.
    Returns the raw response message object (may contain tool_calls or plain text).
    """
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )
    return response.choices[0].message
