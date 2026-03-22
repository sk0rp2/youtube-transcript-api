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

    def test_get_transcript_returns_serialized_transcript(self) -> None:
        transcript = Mock()
        transcript.language = "en"
        transcript.to_raw_data.return_value = [
            {"text": "Hello"},
            {"text": "world"},
        ]

        with patch("main.fetch_best_transcript", return_value=transcript):
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

    def test_fetch_best_transcript_falls_back_to_non_english_available_subtitles(self) -> None:
        fetched = Mock()
        fetched.to_raw_data.return_value = [{"text": "Czesc"}]
        fetched.language = "Polish (auto-generated)"

        transcript = Mock()
        transcript.is_generated = True
        transcript.fetch.return_value = fetched

        transcript_list = Mock()
        transcript_list.__iter__ = Mock(return_value=iter([transcript]))

        with patch("main.YouTubeTranscriptApi") as api_class:
            api_class.return_value.list.return_value = transcript_list

            result = main.fetch_best_transcript("RXjmlRn5Vk4")

        self.assertIs(result, fetched)

    def test_fetch_best_transcript_prefers_configured_language_order(self) -> None:
        fetched_pl = Mock()
        fetched_en = Mock()

        transcript_pl = Mock()
        transcript_pl.language_code = "pl"
        transcript_pl.is_generated = True
        transcript_pl.fetch.return_value = fetched_pl

        transcript_en = Mock()
        transcript_en.language_code = "en"
        transcript_en.is_generated = False
        transcript_en.fetch.return_value = fetched_en

        transcript_list = Mock()
        transcript_list.__iter__ = Mock(return_value=iter([transcript_en, transcript_pl]))

        with patch("main.YouTubeTranscriptApi") as api_class, patch.object(
            main, "TRANSCRIPT_LANGUAGES", ["pl", "en"]
        ):
            api_class.return_value.list.return_value = transcript_list

            result = main.fetch_best_transcript("RXjmlRn5Vk4")

        self.assertIs(result, fetched_pl)

    def test_fetch_best_transcript_prefers_manual_over_generated_for_same_language(self) -> None:
        fetched_manual = Mock()
        fetched_auto = Mock()

        transcript_auto = Mock()
        transcript_auto.language_code = "pl"
        transcript_auto.is_generated = True
        transcript_auto.fetch.return_value = fetched_auto

        transcript_manual = Mock()
        transcript_manual.language_code = "pl"
        transcript_manual.is_generated = False
        transcript_manual.fetch.return_value = fetched_manual

        transcript_list = Mock()
        transcript_list.__iter__ = Mock(return_value=iter([transcript_auto, transcript_manual]))

        with patch("main.YouTubeTranscriptApi") as api_class, patch.object(
            main, "TRANSCRIPT_LANGUAGES", ["pl", "en"]
        ):
            api_class.return_value.list.return_value = transcript_list

            result = main.fetch_best_transcript("RXjmlRn5Vk4")

        self.assertIs(result, fetched_manual)

    def test_get_transcript_from_url_uses_extracted_video_id(self) -> None:
        transcript = Mock()
        transcript.language = "en"
        transcript.to_raw_data.return_value = [{"text": "Hello"}]

        with patch("main.fetch_best_transcript", return_value=transcript):
            result = asyncio.run(main.get_transcript_from_url("https://youtu.be/dQw4w9WgXcQ"))

        self.assertEqual(
            result,
            {
                "videoId": "dQw4w9WgXcQ",
                "text": "Hello",
                "source": "youtube_transcript_api",
                "language": "en",
            },
        )


if __name__ == "__main__":
    unittest.main()
