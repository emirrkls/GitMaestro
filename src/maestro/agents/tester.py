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
        requested = context.get("test_commands")
        if isinstance(requested, list) and requested:
            commands = [str(c) for c in requested]
        elif context.get("test_command"):
            commands = [str(context["test_command"])]
        else:
            scoped = self.test_runner.issue_scoped_commands(context)
            discovered = self.test_runner.discover_commands()
            commands = scoped + [c for c in discovered if c not in scoped]

        attempts: list[dict[str, object]] = []
        chosen_result: dict[str, object] | None = None
        chosen_command = ""
        for command in commands:
            result = self.test_runner.run(command)
            no_tests = self.test_runner.looks_like_no_tests(result)
            infra_error = self.test_runner.looks_like_infra_error(result)
            attempts.append(
                {
                    "command": command,
                    "passed": result["passed"],
                    "exit_code": result["exit_code"],
                    "no_tests_ran": no_tests,
                    "infra_error": infra_error,
                }
            )
            chosen_result = result
            chosen_command = command
            if result["passed"]:
                break
            if not no_tests and not infra_error:
                break

        if chosen_result is None:
            chosen_result = {"passed": False, "exit_code": 127, "stdout": "", "stderr": "No test command discovered."}
            chosen_command = "N/A"

        summary = "Tests passed." if chosen_result["passed"] else "Tests failed."
        return AgentResult(
            summary=summary,
            payload={
                "command": chosen_command,
                "passed": chosen_result["passed"],
                "exit_code": chosen_result["exit_code"],
                "stdout": chosen_result["stdout"],
                "stderr": chosen_result["stderr"],
                "attempts": attempts,
            },
            confidence=0.85 if chosen_result["passed"] else 0.55,
        )
