"""Narrow draft/build/review clients. Live adapter stays disabled without policy."""

import json

from .models import (
    KIND_AUTH,
    KIND_DISABLED,
    KIND_OK,
    KIND_RATE_LIMIT,
    ClientResult,
)


class ExecutionDisabled(Exception):
    pass


class FakeClients:
    def __init__(self, script=None):
        self.script = list(script or [])
        self.calls = []

    def _next(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if self.script:
            item = self.script.pop(0)
            if callable(item):
                return item(name, kwargs)
            return item
        if name == "review":
            return ClientResult(
                kind=KIND_OK,
                text=json.dumps({"verdict": "pass", "explanation": "ok"}),
            )
        return ClientResult(kind=KIND_OK, text="# PRD\nrequirement covered\n")

    async def draft(self, requirement, project):
        return await self._awaited(self._next("draft", requirement=requirement, project=project))

    async def build(self, prd, prior_review, project):
        return await self._awaited(self._next("build", prd=prd, prior_review=prior_review, project=project))

    async def review(self, prd, build_report, project):
        return await self._awaited(self._next("review", prd=prd, build_report=build_report, project=project))

    async def _awaited(self, value):
        if hasattr(value, "__await__"):
            return await value
        return value


class DisabledLiveClients:
    async def draft(self, requirement, project):
        return ClientResult(kind=KIND_DISABLED, text="live execution disabled")

    async def build(self, prd, prior_review, project):
        return ClientResult(kind=KIND_DISABLED, text="live execution disabled")

    async def review(self, prd, build_report, project):
        return ClientResult(kind=KIND_DISABLED, text="live execution disabled")


def classify_known_failure(text):
    lowered = (text or "").lower()
    if "unauthorized" in lowered or "auth" in lowered and "fail" in lowered:
        return KIND_AUTH
    if "rate limit" in lowered or "429" in lowered:
        return KIND_RATE_LIMIT
    return None


def clients_from_policy(execution_policy, fake=None):
    if fake is not None:
        return fake
    if execution_policy is None:
        return DisabledLiveClients()
    if execution_policy.get("enabled") is True:
        from .live_clients import LiveClients

        return LiveClients(execution_policy)
    return DisabledLiveClients()
