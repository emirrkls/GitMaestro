import unittest

from maestro.providers.llm.ollama_provider import _extract_choice_text, _think_request_value


class OllamaProviderHelpersTests(unittest.TestCase):
    def test_think_request_value(self) -> None:
        self.assertIsNone(_think_request_value(False))
        self.assertIs(_think_request_value(True), True)
        self.assertEqual(_think_request_value("low"), "low")
        self.assertEqual(_think_request_value("HIGH"), "high")

    def test_extract_prefers_content_then_reasoning(self) -> None:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": '{"ok": true}',
                        "reasoning": "step by step",
                    }
                }
            ]
        }
        self.assertEqual(_extract_choice_text(payload), '{"ok": true}')

    def test_extract_fallback_to_reasoning(self) -> None:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "reasoning": "only reasoning",
                    }
                }
            ]
        }
        self.assertEqual(_extract_choice_text(payload), "only reasoning")

    def test_extract_fallback_to_thinking_key(self) -> None:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "  ",
                        "thinking": "trace",
                    }
                }
            ]
        }
        self.assertEqual(_extract_choice_text(payload), "trace")


if __name__ == "__main__":
    unittest.main()
