"""Synchronous bridge to opt-in MCP stdio servers."""

import asyncio
from contextlib import AsyncExitStack
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from threading import Event, Thread
from time import monotonic

from coding_agent.contracts import ToolCall, ToolResult


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    command: str
    args: list[str]
    env_from: list[str]
    read_only_tools: list[str]

    @classmethod
    def from_dict(cls, data: dict) -> "MCPServerConfig":
        if (type(data) is not dict
            or not {"name", "command"} <= set(data)
            or set(data) - {"name", "command", "args", "env_from", "read_only_tools"}
            or type(data["name"]) is not str
            or re.fullmatch(r"[A-Za-z0-9_]+", data["name"]) is None
            or type(data["command"]) is not str or not data["command"]
            or any(type(data.get(key, [])) is not list
                   or any(type(item) is not str for item in data.get(key, []))
                   for key in ("args", "env_from", "read_only_tools"))):
            raise ValueError("Invalid MCP server configuration")
        return cls(
            data["name"], data["command"], data.get("args", []),
            data.get("env_from", []), data.get("read_only_tools", []),
        )


class MCPBridge:
    def __init__(self, servers: list[dict], timeout_seconds: int, workspace: Path) -> None:
        self.servers = [MCPServerConfig.from_dict(server) for server in servers]
        if len({server.name for server in self.servers}) != len(self.servers):
            raise ValueError("MCP server names must be unique")
        self.timeout_seconds = timeout_seconds
        self.workspace = workspace
        self.tool_specs: list[dict] = []
        self.targets: dict[str, tuple[str, str]] = {}
        self.write_tools: set[str] = set()
        self._clients: dict[str, object] = {}
        self._ready = Event()
        self._error: Exception | None = None
        self._thread: Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop: asyncio.Event | None = None

    def __enter__(self) -> "MCPBridge":
        if not self.servers:
            return self
        self._thread = Thread(target=self._thread_main, daemon=True)
        self._thread.start()
        if not self._ready.wait(self.timeout_seconds):
            self.__exit__(None, None, None)
            raise RuntimeError("MCP tool discovery timed out")
        if self._error is not None:
            self.__exit__(None, None, None)
            raise RuntimeError(f"MCP connection failed: {self._error}") from self._error
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._thread is not None and self._stop is not None and self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread is not None:
            self._thread.join(self.timeout_seconds + 2)

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as error:
            self._error = error
            self._ready.set()

    async def _serve(self) -> None:
        from mcp import Client, StdioServerParameters

        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        async with AsyncExitStack() as stack:
            for server in self.servers:
                environment = {
                    "PATH": os.environ.get("PATH", ""),
                    "HOME": os.environ.get("HOME", ""),
                }
                environment.update({name: os.environ[name] for name in server.env_from})
                client = await asyncio.wait_for(stack.enter_async_context(Client(
                    StdioServerParameters(
                        command=server.command, args=server.args, env=environment,
                        cwd=self.workspace,
                    )
                )), timeout=self.timeout_seconds)
                self._clients[server.name] = client
                cursor = None
                while True:
                    listing = await asyncio.wait_for(
                        client.list_tools(cursor=cursor), timeout=self.timeout_seconds,
                    )
                    for tool in listing.tools:
                        safe_name = re.sub(r"[^A-Za-z0-9_]", "_", tool.name)
                        model_name = f"mcp__{server.name}__{safe_name}"[:64]
                        if model_name in self.targets:
                            raise ValueError(f"Duplicate MCP tool name: {model_name}")
                        self.targets[model_name] = (server.name, tool.name)
                        self.tool_specs.append({
                            "name": model_name,
                            "description": tool.description or f"MCP tool {tool.name}",
                            "parameters": tool.input_schema,
                        })
                        if tool.name not in server.read_only_tools:
                            self.write_tools.add(model_name)
                    cursor = listing.next_cursor
                    if cursor is None:
                        break
            self._ready.set()
            await self._stop.wait()

    def handles(self, name: str) -> bool:
        return name in self.targets

    def execute(self, call: ToolCall) -> ToolResult:
        started = monotonic()
        server_name, tool_name = self.targets[call.name]
        client = self._clients[server_name]
        future = asyncio.run_coroutine_threadsafe(
            client.call_tool(tool_name, call.arguments), self._loop,
        )
        try:
            result = future.result(timeout=self.timeout_seconds)
        except FutureTimeout:
            future.cancel()
            return ToolResult(call.call_id, call.name, "timeout", "", "MCP tool timed out", None,
                              int((monotonic() - started) * 1000))
        except Exception as error:
            return ToolResult(call.call_id, call.name, "error", "", str(error), None,
                              int((monotonic() - started) * 1000))
        parts = [block.text for block in result.content if block.type == "text"]
        if not parts and result.structured_content is not None:
            parts.append(json.dumps(result.structured_content, ensure_ascii=False))
        output = "\n".join(parts)[:20000]
        return ToolResult(
            call.call_id, call.name, "error" if result.is_error else "completed",
            "" if result.is_error else output,
            output if result.is_error else None,
            None, int((monotonic() - started) * 1000),
        )
