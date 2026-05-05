from __future__ import annotations

from maestro.agents.base import AgentResult, BaseAgent
from maestro.providers.llm.base import LLMProvider
from maestro.providers.test_runner import TestRunner


class TesterAgent(BaseAgent):
    name = "Tester"

    def __init__(self, llm: LLMProvider, model: str, test_runner: TestRunner) -> None:
        super().__init__(llm=llm, model=model)
        self.test_runner = test_runner

    def run(self, context: dict[str, object]) -> AgentResult:
        command = str(context.get("test_command", "python -m unittest discover"))
        result = self.test_runner.run(command)
        summary = "Tests passed." if result["passed"] else "Tests failed."
        return AgentResult(
            summary=summary,
            payload={
                "command": command,
                "passed": result["passed"],
                "exit_code": result["exit_code"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
            },
            confidence=0.85 if result["passed"] else 0.55,
        )
