"""A minimal OpenAI-style tool loop behind the Gauntlet gateway. Runs offline: the model client
is a stub that asks for a 20000 cent refund. Shadow mode lets it through and records what
enforce mode would have done; enforce mode blocks it.

    uv run python examples/gateway/openai_tools.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from gauntlet_core.gateway import Guard, MemorySink, PolicyBlocked

POLICY = Path(__file__).with_name("policy.yaml")


class StubClient:
    """Stands in for `client.chat.completions.create`: one tool call, then a final answer."""

    def create(self, messages: list[dict]) -> SimpleNamespace:
        if messages[-1]["role"] == "tool":
            return SimpleNamespace(content=f"Done: {messages[-1]['content']}", tool_calls=[])
        call = SimpleNamespace(
            function=SimpleNamespace(
                name="issue_refund",
                arguments=json.dumps({"order_id": "ord_1", "amount_cents": 20000}),
            )
        )
        return SimpleNamespace(content=None, tool_calls=[call])


async def run(mode: str) -> tuple[str, list]:
    sink = MemorySink()
    guard = Guard(POLICY, mode=mode, sink=sink, on_block="return")  # type: ignore[arg-type]

    @guard.tool(risk="financial")
    def issue_refund(order_id: str, amount_cents: int) -> dict:
        return {"refunded": amount_cents, "order": order_id}

    tools = {"issue_refund": issue_refund}
    client, messages = StubClient(), [{"role": "user", "content": "Refund order ord_1 fully"}]
    async with guard.session().active() as session:
        while True:
            reply = client.create(messages)
            if not reply.tool_calls:
                await session.check_output(reply.content)
                return reply.content, sink.records
            for tc in reply.tool_calls:
                try:
                    out = await tools[tc.function.name](**json.loads(tc.function.arguments))
                except PolicyBlocked as e:  # only with on_block="raise"
                    out = {"error": str(e)}
                messages.append({"role": "tool", "content": json.dumps(out)})


async def main() -> None:
    for mode in ("shadow", "enforce"):
        answer, records = await run(mode)
        rec = records[0]
        print(f"{mode}: {answer}")
        print(f"  decision: action={rec.action} would_have={rec.would_have} rule={rec.rule_id}")


if __name__ == "__main__":
    asyncio.run(main())
