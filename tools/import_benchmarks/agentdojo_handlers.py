"""Pure ports of the AgentDojo banking and slack suite tools (MIT, ETH SPY Lab; see
benchmarks/NOTICES.md). State layout (flattened from the upstream environment.yaml):

banking: `account/main` (balance, iban), `transactions/<id>`, `scheduled/<id>`, `files/<path>`
(content), `user/user` (name, street, city, user_password).
slack: `users/<name>` (channels, inbox), `channels/<name>` (messages), `web/web` (content map,
requests list).

Reviewed by the lead; the sender of messages we send is `bot`."""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

from gauntlet_core.schema import Json, PatchOp
from gauntlet_core.world import ToolOutcome, WorldView

SENDER = "bot"


def _err(msg: str) -> ToolOutcome:
    return ToolOutcome(error=msg)


def _replace(collection: str, old: Any, new: Any) -> PatchOp:
    return PatchOp(op="replace", collection=collection, id=old["id"], value=new, before=old)


def _acct(view: WorldView) -> Any:
    return view.get("account", "main")


def _next_id(view: WorldView) -> int:
    ids = [int(r["id"]) for c in ("transactions", "scheduled") for r in view.list(c)]
    return max(ids, default=0) + 1


# ------------------------------------------------------------------------------- banking
def get_balance(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    return ToolOutcome(result=_acct(view)["balance"])


def get_iban(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    return ToolOutcome(result=_acct(view)["iban"])


def _by_id(rows: list[Any]) -> list[Any]:
    return sorted(rows, key=lambda r: int(r["id"]))


def get_most_recent_transactions(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    n = int(args.get("n", 100))
    return ToolOutcome(result=_by_id(view.list("transactions"))[-n:] if n > 0 else [])


def get_scheduled_transactions(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    return ToolOutcome(result=_by_id(view.list("scheduled")))


def send_money(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    tid = str(_next_id(view))
    rec = {
        "id": tid,
        "sender": _acct(view)["iban"],
        "recipient": args["recipient"],
        "amount": args["amount"],
        "subject": args["subject"],
        "date": args["date"],
        "recurring": False,
    }
    return ToolOutcome(
        result={"message": f"Transaction to {args['recipient']} for {args['amount']} sent."},
        patch=[PatchOp(op="add", collection="transactions", id=tid, value=rec)],
    )


def schedule_transaction(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    tid = str(_next_id(view))
    rec = {
        "id": tid,
        "sender": _acct(view)["iban"],
        "recipient": args["recipient"],
        "amount": args["amount"],
        "subject": args["subject"],
        "date": args["date"],
        "recurring": bool(args["recurring"]),
    }
    return ToolOutcome(
        result={"message": f"Transaction to {args['recipient']} for {args['amount']} scheduled."},
        patch=[PatchOp(op="add", collection="scheduled", id=tid, value=rec)],
    )


def update_scheduled_transaction(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    old = view.get("scheduled", str(args["id"]))
    if old is None:
        return _err("Transaction with ID not found.")
    new = {**old, **{k: v for k, v in args.items() if k != "id" and v is not None}}
    return ToolOutcome(
        result={"message": f"Transaction with ID {args['id']} updated."},
        patch=[_replace("scheduled", old, new)],
    )


def read_file(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    f = view.get("files", str(args["file_path"]))
    return _err("File not found.") if f is None else ToolOutcome(result=f["content"])


def get_user_info(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    u: Any = view.get("user", "user")
    return ToolOutcome(result={k: u[k] for k in ("first_name", "last_name", "street", "city")})


def update_password(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    u: Any = view.get("user", "user")
    new = {**u, "user_password": args["password"]}
    return ToolOutcome(result={"message": "Password updated."}, patch=[_replace("user", u, new)])


def update_user_info(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    u: Any = view.get("user", "user")
    keys = ("first_name", "last_name", "street", "city")
    new = {**u, **{k: args[k] for k in keys if args.get(k) is not None}}
    info = {k: new[k] for k in keys}
    return ToolOutcome(result=info, patch=[_replace("user", u, new)])


# --------------------------------------------------------------------------------- slack
def get_channels(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    return ToolOutcome(result=sorted(c["id"] for c in view.list("channels")))


def read_channel_messages(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    ch = view.get("channels", str(args["channel"]))
    return _err("Channel does not exist!") if ch is None else ToolOutcome(result=ch["messages"])


def read_inbox(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    u = view.get("users", str(args["user"]))
    return _err("User does not exist!") if u is None else ToolOutcome(result=u["inbox"])


def send_direct_message(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    u: Any = view.get("users", str(args["recipient"]))
    if u is None:
        return _err("Recipient does not exist!")
    new = copy.deepcopy(u)
    new["inbox"].append({"sender": SENDER, "recipient": args["recipient"], "body": args["body"]})
    return ToolOutcome(result=None, patch=[_replace("users", u, new)])


def send_channel_message(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    ch: Any = view.get("channels", str(args["channel"]))
    if ch is None:
        return _err("Channel does not exist!")
    new = copy.deepcopy(ch)
    new["messages"].append({"sender": SENDER, "recipient": args["channel"], "body": args["body"]})
    return ToolOutcome(result=None, patch=[_replace("channels", ch, new)])


def add_user_to_channel(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    u: Any = view.get("users", str(args["user"]))
    if u is None:
        return _err("User does not exist!")
    if view.get("channels", str(args["channel"])) is None:
        return _err("Channel does not exist!")
    new = {**u, "channels": sorted({*u["channels"], str(args["channel"])})}
    return ToolOutcome(result=None, patch=[_replace("users", u, new)])


def get_users_in_channel(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    if view.get("channels", str(args["channel"])) is None:
        return _err("Channel does not exist!")
    names = sorted(u["id"] for u in view.list("users") if args["channel"] in u["channels"])
    return ToolOutcome(result=names)


def invite_user_to_slack(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    name = str(args["user"])
    if view.get("users", name) is not None:
        return _err("User already in Slack!")
    rec = {"id": name, "channels": [], "inbox": [], "email": args["user_email"]}
    return ToolOutcome(
        result=None, patch=[PatchOp(op="add", collection="users", id=name, value=rec)]
    )


def remove_user_from_slack(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    u: Any = view.get("users", str(args["user"]))
    if u is None:
        return _err("User does not exist!")
    return ToolOutcome(
        result=None, patch=[PatchOp(op="remove", collection="users", id=u["id"], before=u)]
    )


def get_webpage(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    web: Any = view.get("web", "web")
    new = {**web, "requests": [*web["requests"], args["url"]]}
    text = web["content"].get(str(args["url"]), "404 Not Found")
    return ToolOutcome(result=text, patch=[_replace("web", web, new)])


def post_webpage(view: WorldView, args: Json, now: datetime) -> ToolOutcome:
    web: Any = view.get("web", "web")
    new = {
        **web,
        "requests": [*web["requests"], args["url"]],
        "content": {**web["content"], str(args["url"]): args["content"]},
    }
    return ToolOutcome(result=None, patch=[_replace("web", web, new)])
