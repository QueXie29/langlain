from django.test import SimpleTestCase

from knowledge.services.chunking import chunk_text, normalize_text


class ChunkingTests(SimpleTestCase):
    def test_normalize_text(self):
        self.assertEqual(normalize_text("第一行  \r\n\r\n\r\n第二行"), "第一行 \n\n第二行")

    def test_short_text_is_one_chunk(self):
        self.assertEqual(chunk_text("这是一个短文档。", chunk_size=20, overlap=5), ["这是一个短文档。"])

    def test_chunks_overlap_and_do_not_loop(self):
        chunks = chunk_text("第一句。第二句。第三句。第四句。", chunk_size=10, overlap=2)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunks))
        self.assertLess(len(chunks), 10)

    def test_rejects_invalid_configuration(self):
        with self.assertRaises(ValueError):
            chunk_text("text", chunk_size=10, overlap=10)

    def test_long_unbroken_text_preserves_overlap(self):
        text = "abcdefghijklmnopqrstuvwxyz"
        chunks = chunk_text(text, chunk_size=10, overlap=3)
        self.assertTrue(all(len(chunk) <= 10 for chunk in chunks))
        for previous, following in zip(chunks, chunks[1:]):
            self.assertEqual(previous[-3:], following[:3])
        self.assertEqual(chunks[0] + "".join(chunk[3:] for chunk in chunks[1:]), text)

    def test_chinese_punctuation_is_preserved(self):
        text = "第一句话。第二句话！第三句话？第四句话；"
        chunks = chunk_text(text, chunk_size=10, overlap=0)
        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(len(chunk) <= 10 for chunk in chunks))
