import asyncio
import unittest

from interview_forge.ai.provider import _content_text, stream_chat_chunks, visible_text


class Chunk:
    def __init__(self, content):
        self.content = content
        self.tool_call_chunks = []
        self.additional_kwargs = {}


class ProviderTextNormalizationTests(unittest.TestCase):
    def test_string_chunks_remain_visible(self):
        chunk = Chunk("你好")
        self.assertEqual(visible_text(chunk), "你好")
        self.assertEqual(_content_text("继续"), "继续")

    def test_text_blocks_are_visible_and_reasoning_blocks_are_dropped(self):
        content = [
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": "hidden"}]},
            {"type": "text", "text": "你好"},
            {"type": "output_text", "text": "，世界"},
        ]
        self.assertEqual(visible_text(Chunk(content)), "你好，世界")
        self.assertEqual(_content_text([{"type": "reasoning"}]), "")

    def test_stream_adapter_uses_the_same_normalizer(self):
        class Model:
            async def astream(self, _messages):
                yield Chunk("")
                yield Chunk([{"type": "reasoning"}])
                yield Chunk([{"type": "text", "text": "有效回答"}])

        async def collect():
            return [item async for item in stream_chat_chunks(Model(), [])]

        self.assertEqual(asyncio.run(collect()), [("", {}), ("", {}), ("有效回答", {})])


if __name__ == "__main__":
    unittest.main()
