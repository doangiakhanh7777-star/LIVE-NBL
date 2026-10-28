"""4.3.0: AI trả lời bình luận — từ khóa, nhiều key, đọc câu trả lời/âm thanh của Gemini (không gọi mạng)."""
import base64, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_reply as A


class Rules(unittest.TestCase):
    def test_keywords_first_most_specific_wins(self):
        r = A.parse_rules('bơm lốp;bom lop | Anh xem bơm lốp trong giỏ nhé\ngiá | Giá trong giỏ ạ\nbao nhiêu tiền | Giá ghi trong giỏ ạ')
        self.assertEqual(A.rule_answer(r, 'Bơm lốp giá sao em'), 'Anh xem bơm lốp trong giỏ nhé')
        self.assertEqual(A.rule_answer(r, 'cái này bao nhiêu tiền'), 'Giá ghi trong giỏ ạ')
        self.assertIsNone(A.rule_answer(r, 'giao hàng mấy ngày'))      # "gia" is not "giao"


class Keys(unittest.TestCase):
    def test_out_of_quota_key_rests_and_the_next_one_answers(self):
        calls = []
        def f(k):
            calls.append(k)
            if k == 'a':
                raise A.AIError('Gemini đang giới hạn lượt dùng')
            return 'ok'
        ring = A.KeyRing(['a', 'b'], clock=lambda: 100)
        self.assertEqual(ring.call(f), 'ok'); self.assertEqual(calls, ['a', 'b'])
        self.assertEqual(ring.usable(), ['b'])

    def test_all_wrong_keys_say_so(self):
        def f(k):
            raise A.AIError('API key Gemini không đúng hoặc chưa được bật.')
        with self.assertRaisesRegex(A.AIError, 'sai'):
            A.KeyRing(['a', 'b']).call(f)

    def test_no_key(self):
        with self.assertRaisesRegex(A.AIError, 'Chưa nhập'):
            A.KeyRing([]).call(lambda k: 'x')


class Answers(unittest.TestCase):
    def test_interactions_and_old_shapes(self):
        self.assertEqual(A.answer_text({'steps': [{'type': 'user_input', 'content': [{'type': 'text', 'text': 'q'}]},
                                                  {'type': 'model_output', 'content': [{'type': 'text', 'text': 'Dạ có ạ'}]}]}), 'Dạ có ạ')
        self.assertEqual(A.answer_text({'candidates': [{'content': {'parts': [{'text': 'Dạ '}, {'text': 'còn hàng'}]}}]}), 'Dạ còn hàng')

    def test_skip_and_length(self):
        self.assertEqual(A.clean_answer('SKIP'), '')
        self.assertLessEqual(len(A.clean_answer('a' * 300)), A.MAX_CHARS)
        self.assertEqual(A.clean_answer('**Dạ** có ạ'), 'Dạ có ạ')

    def test_audio_wav_or_pcm(self):
        wav = A.pcm_to_wav(b'\0\0' * 100)
        g = A.Gemini('k', post=lambda url, body, key, timeout=0: {'steps': [{'content': [{'type': 'audio', 'data': base64.b64encode(wav).decode()}]}]})
        self.assertEqual(g.speak('xin chào')[:4], b'RIFF')
        g = A.Gemini('k', post=lambda url, body, key, timeout=0: {'candidates': [{'content': {'parts': [{'inlineData': {'mimeType': 'audio/L16;rate=24000', 'data': base64.b64encode(b'\0\0' * 50).decode()}}]}}]})
        self.assertEqual(g.speak('xin chào')[:4], b'RIFF')

    def test_unknown_model_falls_back_to_generate_content(self):
        seen = []
        def post(url, body, key, timeout=0):
            seen.append(url)
            if url.endswith('interactions'):
                raise A.AIError('404 model: not found')
            return {'candidates': [{'content': {'parts': [{'text': 'Dạ có'}]}}]}
        self.assertEqual(A.Gemini('k', post=post).ask('sys', 'còn hàng không'), 'Dạ có')
        self.assertTrue(seen[-1].endswith(':generateContent'))


if __name__ == '__main__':
    unittest.main()
