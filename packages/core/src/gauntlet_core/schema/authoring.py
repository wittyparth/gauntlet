"""Authoring models: what users and packs write (contracts section 1)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from .checks import Check
from .common import Json, Model, Severity

Risk = Literal["read", "write", "destructive", "financial", "external_comm"]


class Persona(Model):
    id: str
    name: str
    description: str
    traits: dict[str, str | float] = {}
    behavior_rules: list[str] = []
    adversarial_intent: str | None = None


class CrudHandler(Model):
    kind: Literal["crud"] = "crud"
    collection: str
    op: Literal["get", "list", "create", "update", "delete"]
    key_arg: str | None = None
    filter_args: list[str] = []


class PythonHandler(Model):
    kind: Literal["python"] = "python"
    entrypoint: str  # "package.module:function"


class LLMSimHandler(Model):
    kind: Literal["llm_sim"] = "llm_sim"
    instructions: str


class StaticHandler(Model):
    kind: Literal["static"] = "static"
    result: Json


HandlerSpec = Annotated[
    CrudHandler | PythonHandler | LLMSimHandler | StaticHandler, Field(discriminator="kind")
]


class ToolSpec(Model):
    name: str
    description: str
    input_schema: Json = {"type": "object", "properties": {}}
    risk: Risk
    handler: HandlerSpec
    untrusted_output: bool = False
    honeytool: bool = False


FaultKind = Literal[
    "timeout", "http_500", "http_429", "malformed_json", "empty", "stale", "latency", "schema_drift"
]


class FaultSpec(Model):
    tool: str
    kind: FaultKind
    probability: float = Field(default=1.0, ge=0.0, le=1.0)
    on_call_index: int | None = None  # 0-based index among calls to this tool
    params: Json = {}


class CanarySpec(Model):
    id: str
    kind: Literal["api_key", "email", "card", "ssn", "record", "freeform"]
    placement: Literal["system_prompt", "world_record", "document", "tool_result"]
    location: str


class InjectionSpec(Model):
    attack: str
    placement: Literal["body", "footer", "html_comment", "hidden_text", "metadata"] = "body"


class DocumentSpec(Model):
    id: str
    title: str
    body: str
    trusted: bool = True
    injection: InjectionSpec | None = None


class WorldSpec(Model):
    id: str | None = None
    tools: list[ToolSpec] = []
    seed: dict[str, list[Json]] = {}
    clock_start: datetime
    faults: list[FaultSpec] = []
    canaries: list[CanarySpec] = []
    documents: list[DocumentSpec] = []


class NamedCheck(Model):
    id: str
    description: str
    severity: Severity
    check: Check


class AttackRef(Model):
    attack: str
    params: Json = {}


class Scenario(Model):
    id: str
    version: int = 1
    title: str
    goal: str
    persona: str
    persona_overrides: dict[str, str | float] = {}
    hidden_facts: list[str] = []
    opening_message: str | None = None
    world: str | WorldSpec
    world_overrides: Json = {}
    success: Check
    forbidden: list[NamedCheck] = []
    rubrics: list[str] = []
    max_turns: int = Field(default=12, ge=1, le=100)
    tags: dict[str, str] = {}
    attack: AttackRef | None = None


class Suite(Model):
    id: str
    name: str
    scenarios: list[str]
    repetitions: int = Field(default=1, ge=1)
    persona_mix: dict[str, float] | None = None


class AgentProfile(Model):
    purpose: str
    audience: str = ""
    policies_text: str = ""
    forbidden_behaviors: list[str] = []
    languages: list[str] = ["en"]


class HostedTargetConfig(Model):
    kind: Literal["hosted"] = "hosted"
    model: str
    system_prompt: str
    temperature: float = 0.0
    tools: list[str] | None = None


class OpenAICompatTargetConfig(Model):
    kind: Literal["openai_compat"] = "openai_compat"
    base_url: str
    model: str
    api_key_secret: str | None = None
    wired: bool = False


class HttpTargetConfig(Model):
    kind: Literal["http"] = "http"
    url: str
    method: str = "POST"
    headers: dict[str, str] = {}
    body_template: Json
    reply_path: str
    conversation_id_path: str | None = None
    stateful: bool = False
    wired: bool = False


TargetConfig = Annotated[
    HostedTargetConfig | OpenAICompatTargetConfig | HttpTargetConfig, Field(discriminator="kind")
]


class AgentVersion(Model):
    id: str
    agent_id: str
    label: str
    target: TargetConfig
    profile: AgentProfile
