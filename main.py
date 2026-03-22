"""
FastAPI application providing a simple API for retrieving YouTube video transcripts.

Endpoints:

* ``GET /health`` - simple health check returning status.
* ``GET /extract-video-id`` - optional helper that extracts a YouTube video ID from a URL.
* ``GET /transcript`` - returns the transcript text for a given ``videoId``.

Security:

The API uses a simple API key mechanism. An API key must be provided in the
``X-API-Key`` request header. The expected key is configured via the
``API_KEY`` environment variable. If no key is configured, the API will
not enforce authentication (useful during local development).
"""

import os
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security.api_key import APIKeyHeader
from youtube_transcript_api import CouldNotRetrieveTranscript, YouTubeTranscriptApi

load_dotenv()

VIDEO_ID_PATTERN = re.compile(r"^[0-9A-Za-z_-]{11}$")

# Read API key from environment. Do not hard-code secrets in the code.
API_KEY: Optional[str] = os.getenv("API_KEY")
TRANSCRIPT_LANGUAGES = [
    language.strip()
    for language in os.getenv("TRANSCRIPT_LANGUAGES", "").split(",")
    if language.strip()
]

# Header object to extract the API key from requests. Setting ``auto_error=False``
# allows us to handle missing keys manually.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

app = FastAPI(title="YouTube Transcript API", version="1.0.0")


def is_valid_video_id(video_id: str) -> bool:
    """Return True when the input matches the canonical YouTube video ID format."""
    return bool(VIDEO_ID_PATTERN.fullmatch(video_id))


def extract_video_id_from_url(url: str) -> Optional[str]:
    """Extract a YouTube video ID from common YouTube URL formats."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.strip("/")

    if host == "youtu.be":
        candidate = path.split("/", 1)[0]
        return candidate if is_valid_video_id(candidate) else None

    if host in {"youtube.com", "m.youtube.com"}:
        if path == "watch":
            candidate = parse_qs(parsed.query).get("v", [None])[0]
            return candidate if candidate and is_valid_video_id(candidate) else None

        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live", "v"}:
            candidate = parts[1]
            return candidate if is_valid_video_id(candidate) else None

    return None


def fetch_best_transcript(video_id: str):
    """Fetch the best available transcript for a video.

    When ``TRANSCRIPT_LANGUAGES`` is configured, language order is respected
    first and manual transcripts are preferred over auto-generated ones within
    each language. If none of the preferred languages is available, the
    function falls back to the first available transcript, still preferring
    manual transcripts.
    """
    transcript_list = YouTubeTranscriptApi().list(video_id)
    transcripts = list(transcript_list)
    if not transcripts:
        raise CouldNotRetrieveTranscript(video_id)

    for language_code in TRANSCRIPT_LANGUAGES:
        language_matches = [
            transcript for transcript in transcripts if transcript.language_code == language_code
        ]
        if language_matches:
            language_matches.sort(key=lambda transcript: transcript.is_generated)
            return language_matches[0].fetch()

    transcripts.sort(key=lambda transcript: transcript.is_generated)
    return transcripts[0].fetch()


def serialize_transcript(video_id: str, transcript) -> dict:
    """Convert a fetched transcript object into the public API response shape."""
    transcript_items = transcript.to_raw_data()
    response = {
        "videoId": video_id,
        "text": " ".join(entry.get("text", "") for entry in transcript_items),
        "source": "youtube_transcript_api",
    }
    if transcript.language:
        response["language"] = transcript.language
    return response


async def verify_api_key(provided_key: Optional[str] = Depends(api_key_header)) -> None:
    """Dependency that verifies the provided API key."""
    if API_KEY and (not provided_key or provided_key != API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get("/health", tags=["Utility"], summary="Service health check")
async def health() -> dict:
    """Return a simple JSON response indicating the service is running."""
    return {"status": "ok"}


@app.get(
    "/extract-video-id",
    tags=["Utility"],
    summary="Extract a YouTube video ID from a URL",
    responses={
        200: {"description": "Extracted video ID", "content": {"application/json": {"example": {"videoId": "dQw4w9WgXcQ"}}}},
        400: {"description": "Invalid YouTube URL"},
    },
)
async def extract_video_id(url: str, _: None = Depends(verify_api_key)) -> dict:
    """Extract the 11-character YouTube video ID from a full YouTube URL."""
    video_id = extract_video_id_from_url(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    return {"videoId": video_id}


@app.get(
    "/transcript",
    tags=["Transcript"],
    summary="Fetch the transcript for a YouTube video",
    responses={
        200: {
            "description": "Transcript found",
            "content": {
                "application/json": {
                    "example": {
                        "videoId": "dQw4w9WgXcQ",
                        "text": "Never gonna give you up, never gonna let you down...",
                        "language": "en",
                        "source": "youtube_transcript_api",
                    }
                }
            },
        },
        400: {"description": "Invalid YouTube video ID"},
        404: {"description": "Transcript not available"},
        500: {"description": "Unexpected error"},
    },
)
async def get_transcript(videoId: str, _: None = Depends(verify_api_key)) -> dict:
    """Retrieve the transcript text for the specified YouTube video ID."""
    if not is_valid_video_id(videoId):
        raise HTTPException(status_code=400, detail="Invalid YouTube video ID")

    try:
        transcript = fetch_best_transcript(videoId)
    except CouldNotRetrieveTranscript:
        raise HTTPException(status_code=404, detail="Transcript not available for this video")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return serialize_transcript(videoId, transcript)


@app.get(
    "/transcript-from-url",
    tags=["Transcript"],
    summary="Fetch the transcript for a YouTube URL",
    responses={
        200: {
            "description": "Transcript found",
            "content": {
                "application/json": {
                    "example": {
                        "videoId": "dQw4w9WgXcQ",
                        "text": "Never gonna give you up, never gonna let you down...",
                        "language": "en",
                        "source": "youtube_transcript_api",
                    }
                }
            },
        },
        400: {"description": "Invalid YouTube URL"},
        404: {"description": "Transcript not available"},
        500: {"description": "Unexpected error"},
    },
)
async def get_transcript_from_url(url: str, _: None = Depends(verify_api_key)) -> dict:
    """Retrieve the transcript text for the specified YouTube URL."""
    video_id = extract_video_id_from_url(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    try:
        transcript = fetch_best_transcript(video_id)
    except CouldNotRetrieveTranscript:
        raise HTTPException(status_code=404, detail="Transcript not available for this video")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return serialize_transcript(video_id, transcript)
