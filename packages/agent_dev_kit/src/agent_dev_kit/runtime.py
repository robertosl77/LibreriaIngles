from dataclasses import dataclass
from typing import Any, Mapping

from agents import Agent, Runner

from .config import ProjectConfig


@dataclass(slots=True)
class DevAgentKit:
    config: ProjectConfig
    triage_agent: Agent
    specialists: Mapping[str, Agent]

    def conversation(self, *, session: Any | None = None) -> "DevConversation":
        return DevConversation(
            kit=self,
            session=session,
            active_agent=self.triage_agent,
        )


@dataclass(slots=True)
class DevConversation:
    kit: DevAgentKit
    session: Any | None = None
    active_agent: Agent | None = None

    @property
    def current_agent_name(self) -> str:
        agent = self.active_agent or self.kit.triage_agent
        return agent.name

    def reset_route(self) -> None:
        self.active_agent = self.kit.triage_agent

    async def ask(self, message: str):
        start_agent = self.active_agent or self.kit.triage_agent
        kwargs: dict[str, Any] = {}
        if self.session is not None:
            kwargs["session"] = self.session

        result = await Runner.run(start_agent, message, **kwargs)
        self.active_agent = result.last_agent
        return result

    def ask_sync(self, message: str):
        start_agent = self.active_agent or self.kit.triage_agent
        kwargs: dict[str, Any] = {}
        if self.session is not None:
            kwargs["session"] = self.session

        result = Runner.run_sync(start_agent, message, **kwargs)
        self.active_agent = result.last_agent
        return result
