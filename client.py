from __future__ import annotations

from typing import Any

import httpx

from models import PatchAction, PatchState


class EnvClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.get("/health")
            response.raise_for_status()
            return response.json()

    async def tasks(self) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.get("/tasks")
            response.raise_for_status()
            return response.json()

    async def reset(self, task_name: str = "easy_patch") -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post("/reset", json={"task_name": task_name})
            response.raise_for_status()
            return response.json()

    async def step(self, action: PatchAction) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post("/step", json=action.model_dump())
            response.raise_for_status()
            return response.json()

    async def state(self) -> PatchState:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.get("/state")
            response.raise_for_status()
            return PatchState.model_validate(response.json())
