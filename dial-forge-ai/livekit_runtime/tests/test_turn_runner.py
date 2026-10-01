import json
import unittest

from livekit_runtime.tools import DialForgeToolHandlers
from livekit_runtime.turn_runner import RuntimeCapabilityTurnRunner
from runtime.vocabulary import KnowledgeBaseResource, RuntimeContext


class Obj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeChatCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.chat = Obj(completions=FakeChatCompletions(responses))


def text_chunk(content):
    return Obj(choices=[Obj(delta=Obj(content=content, tool_calls=None))])


def tool_chunk(index, call_id=None, name=None, arguments=None):
    return Obj(
        choices=[
            Obj(
                delta=Obj(
                    content=None,
                    tool_calls=[
                        Obj(
                            index=index,
                            id=call_id,
                            function=Obj(name=name, arguments=arguments),
                        )
                    ],
                )
            )
        ]
    )


class RuntimeCapabilityTurnRunnerTest(unittest.TestCase):
    def test_streams_plain_response_without_tools(self):
        client = FakeClient(
            responses=[
                [
                    text_chunk("Hello."),
                    text_chunk(" Anything else?"),
                ]
            ]
        )
        sentences = []
        messages = [{"role": "system", "content": "system"}]

        result = RuntimeCapabilityTurnRunner(
            client=client,
            runtime_context=None,
            tools_enabled=False,
        ).run(messages, on_sentence=sentences.append)

        self.assertEqual(sentences, ["Hello.", " Anything else?"])
        self.assertEqual(result.assistant_text, "Hello. Anything else?")
        self.assertEqual(messages[-1], {"role": "assistant", "content": "Hello. Anything else?"})
        self.assertNotIn("tools", client.chat.completions.calls[0])

    def test_executes_runtime_tool_then_gets_final_response(self):
        client = FakeClient(
            responses=[
                [
                    tool_chunk(
                        0,
                        call_id="call_1",
                        name="retrieve_company_kb",
                        arguments='{"query": "what do you do"}',
                    )
                ],
                [
                    text_chunk("We automate phone workflows."),
                ],
            ]
        )
        retrieval_calls = []

        def fake_retrieval_handler(**kwargs):
            retrieval_calls.append(kwargs)
            return [
                {
                    "source_file": "globifye.md",
                    "section": "Overview",
                    "content": "GlobiFYE automates phone workflows.",
                    "distance": 0.1,
                }
            ]

        messages = [{"role": "system", "content": "system"}]
        sentences = []

        result = RuntimeCapabilityTurnRunner(
            client=client,
            runtime_context=self._knowledge_context(),
            handlers=DialForgeToolHandlers(retrieval_handler=fake_retrieval_handler),
        ).run(messages, on_sentence=sentences.append)

        self.assertEqual(result.assistant_text, "We automate phone workflows.")
        self.assertEqual(sentences, ["We automate phone workflows."])
        self.assertEqual(retrieval_calls[0]["company_key"], "globifye")
        self.assertIn("tools", client.chat.completions.calls[0])
        self.assertEqual(len(client.chat.completions.calls), 2)
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["tool_calls"][0]["function"]["name"], "retrieve_company_kb")
        self.assertEqual(messages[2]["role"], "tool")
        tool_result = json.loads(messages[2]["content"])
        self.assertTrue(tool_result["has_evidence"])
        self.assertEqual(messages[-1]["role"], "assistant")

    def test_blocks_tool_call_when_budget_exceeded(self):
        client = FakeClient(
            responses=[
                [
                    tool_chunk(
                        0,
                        call_id="call_1",
                        name="request_handoff",
                        arguments='{"reason": "need a person"}',
                    ),
                    tool_chunk(
                        1,
                        call_id="call_2",
                        name="request_handoff",
                        arguments='{"reason": "need a person again"}',
                    ),
                ],
                [
                    text_chunk("I requested help."),
                ],
            ]
        )

        messages = [{"role": "system", "content": "system"}]

        result = RuntimeCapabilityTurnRunner(
            client=client,
            runtime_context=self._handoff_context(),
            handlers=DialForgeToolHandlers(human_handoff_handler=lambda **kwargs: {"ok": True}),
        ).run(messages)

        self.assertEqual(result.assistant_text, "I requested help.")
        first_tool = json.loads(messages[2]["content"])
        second_tool = json.loads(messages[3]["content"])
        self.assertTrue(first_tool["ok"])
        self.assertFalse(second_tool["ok"])
        self.assertEqual(second_tool["policy"], "max_calls_per_turn")

    def _knowledge_context(self):
        return RuntimeContext(
            agent_config_id="agent-globifye",
            company_key="globifye",
            call_session_id="call-1",
            knowledge_bases=[
                KnowledgeBaseResource(
                    knowledge_profile_id="globifye",
                    company_key="globifye",
                    retrieval_policy={"top_k": 4},
                )
            ],
        )

    def _handoff_context(self):
        return RuntimeContext(
            agent_config_id="agent-globifye",
            company_key="globifye",
            call_session_id="call-1",
            session_state={
                "human_handoff_enabled": True,
                "default_human_endpoint": "PJSIP/sales",
            },
        )


if __name__ == "__main__":
    unittest.main()
