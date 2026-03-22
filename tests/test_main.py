import unittest
from unittest.mock import Mock, patch
import asyncio

import main


class MainTestCase(unittest.TestCase):
    def test_accepts_supported_youtube_urls(self) -> None:
        cases = [
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s",
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "https://m.youtube.com/shorts/dQw4w9WgXcQ",
        ]

        for url in cases:
            with self.subTest(url=url):
                self.assertEqual(main.extract_video_id_from_url(url), "dQw4w9WgXcQ")

    def test_rejects_invalid_urls(self) -> None:
        cases = [
            "https://example.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=invalid",
            "not-a-url",
        ]

        for url in cases:
            with self.subTest(url=url):
                self.assertIsNone(main.extract_video_id_from_url(url))

    def test_validates_video_id_format(self) -> None:
        self.assertTrue(main.is_valid_video_id("dQw4w9WgXcQ"))
        self.assertFalse(main.is_valid_video_id("invalid"))

    def test_get_transcript_uses_current_library_api(self) -> None:
        transcript = Mock()
        transcript.language = "en"
        transcript.to_raw_data.return_value = [
            {"text": "Hello"},
            {"text": "world"},
        ]

        with patch("main.YouTubeTranscriptApi") as api_class:
            api_class.return_value.fetch.return_value = transcript

            result = asyncio.run(main.get_transcript("dQw4w9WgXcQ"))

        self.assertEqual(
            result,
            {
                "videoId": "dQw4w9WgXcQ",
                "text": "Hello world",
                "source": "youtube_transcript_api",
                "language": "en",
            },
        )


if __name__ == "__main__":
    unittest.main()
