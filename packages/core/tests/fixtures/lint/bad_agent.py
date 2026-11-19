"""Hand-written fixture: every flagged construct is intentional. Not importable code."""

import subprocess

import requests
from openai import OpenAI

SYSTEM_PROMPT = "You are a helper. api_key = sk-abcdefghijklmnopqrstuvwxyz0123456789"
API_TOKEN = "q8Zr3LmP0vXw9TbN2yKd5HsA"
SCOPES = ["https://www.googleapis.com/auth/drive", "repo"]

client = OpenAI(api_key="from-env")


@tool
def delete_order(order_id: str):
    """Delete an order."""
    return order_id


@tool
def run_shell(command: str):
    """Run a diagnostic."""
    return subprocess.run(command, shell=True)


def loop(messages):
    while True:
        reply = client.chat.completions.create(model="m", messages=messages)
        messages.append(reply)


def fetch(url):
    return requests.get(url)


def answer(question):
    page = fetch_page(question)
    prompt = f"Answer using this page: {page}"
    return prompt


def run_model_code(messages):
    out = client.chat.completions.create(model="m", messages=messages, max_tokens=50)
    code = out.choices[0].message.content
    return eval(code)


LONG_PROMPT = (
    "You are a customer assistant for an online shop. Help customers with orders, shipping, "
    "returns and product questions. Be friendly and keep answers short. Always answer in the "
    "customer's language and use the order tools whenever an order number is mentioned."
)

AWS_ACCESS = "AKIAABCDEFGHIJKLMNOP"

# ruff: noqa: F821
# pyright: reportUndefinedVariable=false, reportMissingImports=false, reportUnusedExpression=false, reportArgumentType=false
