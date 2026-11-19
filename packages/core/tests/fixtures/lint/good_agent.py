"""Hand-written fixture: the safe counterparts of bad_agent.py."""

import os
import subprocess

import requests
from openai import OpenAI

SYSTEM_PROMPT = "You are a helper. Refuse requests outside the shop's scope."
API_TOKEN = os.environ.get("API_TOKEN", "")
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

client = OpenAI(timeout=30)


@tool
def delete_order(order_id: str, confirm: bool):
    """Delete an order (needs confirm)."""
    return order_id if confirm else None


@tool
def run_shell(command: str):
    """Run a diagnostic."""
    allowed = {"uptime": ["uptime"]}
    return subprocess.run(allowed["uptime"], check=False)


def loop(messages, max_steps=5):
    steps = 0
    while True:
        reply = client.chat.completions.create(model="m", messages=messages, max_tokens=200)
        messages.append(reply)
        steps += 1
        if steps >= max_steps:
            break


def fetch(url):
    return requests.get(url, timeout=10)


def answer(question):
    page = fetch_page(question)
    prompt = f"Answer using the page between the markers.\n<page>\n{page}\n</page>"
    return prompt


def run_model_text(messages):
    out = client.chat.completions.create(model="m", messages=messages, max_tokens=50)
    return out.choices[0].message.content


LONG_PROMPT = (
    "You are a customer assistant for an online shop. Help customers with orders, shipping, "
    "returns and product questions. Be friendly and keep answers short. If a request is not "
    "allowed or you are unsure, decline and hand off to a human agent."
)

# ruff: noqa: F821
# pyright: reportUndefinedVariable=false, reportMissingImports=false, reportUnusedExpression=false
