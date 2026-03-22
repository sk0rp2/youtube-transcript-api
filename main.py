"""
FastAPI application providing a simple API for retrieving YouTube video transcripts.

Endpoints:

* ``GET /health`` – simple health check returning status.
* ``GET /extract-video-id`` – optional helper that extracts a YouTube video ID from a URL.
* ``GET /transcript`` – returns the transcript text for a given ``videoId``.

Security:

The API uses a simple API key mechanism. An API key must be provided in the
``X-API-Key`` request header. The expected key is configured via the
``API_KEY`` environment variable. If no key is configured, the API will
not enforce authentication (useful during local development).
"""

import os
import re
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security.api_key import APIKeyHeader
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptNotFound

# Read API key from environment. Do not hard‑code secrets in the code.
API_KEY: Optional[str] = os.getenv("API_KEY")

# Header object to extract the API key from requests. Setting ``auto_error=False``
# allows us to handle missing keys manually.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

app = FastAPI(title="YouTube Transcript API", version="1.0.0")


async def verify_api_key(provided_key: Optional[str] = Depends(api_key_header)) -> None:
    """Dependency that verifies the provided API key.

    If an API key is configured via the ``API_KEY`` environment variable, this
    function will ensure the incoming request contains a matching key in the
    ``X-API-Key`` header. If the key is missing or invalid, a 401 error is raised.

    If ``API_KEY`` is not set (e.g. during local development), authentication
    is effectively disabled and this dependency does nothing.
    """
    if API_KEY:
        if not provided_key or provided_key != API_KEY:
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
    """
    Extract the 11‑character YouTube video ID from a full YouTube URL.

    The function attempts to match common URL patterns such as
    ``https://www.youtube.com/watch?v=VIDEO_ID`` and
    ``https://youtu.be/VIDEO_ID``. If no valid ID is found, a 400 error is
    returned.

    Parameters
    ----------
    url: str
        Full YouTube URL containing the video ID.

    Returns
    -------
    dict
        JSON object with the extracted ``videoId``.
    """
    # Regular expression capturing the 11‑character video ID from supported URLs.
    match = re.search(r"(?P<id>[0-9A-Za-z_-]{11})(?:&|$)", url)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    return {"videoId": match.group("id")}


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
                        "text": "Never gonna give you up, never gonna let you down…",
                        "language": "en",
                        "source": "youtube_transcript_api",
                    }
                }
            },
        },
        404: {"description": "Transcript not available"},
        500: {"description": "Unexpected error"},
    },
)
async def get_transcript(videoId: str, _: None = Depends(verify_api_key)) -> dict:
    """
    Retrieve the transcript text for the specified YouTube video ID.

    If a transcript is available, the service concatenates all lines into a
    single string and returns it along with the ``videoId`` and source
    identifier. The primary transcript language is included when available.
    """
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(videoId)
    except TranscriptNotFound:
        raise HTTPException(status_code=404, detail="Transcript not available for this video")
    except Exception as exc:
        # Catch any other errors (e.g. network issues) and return 500
        raise HTTPException(status_code=500, detail=str(exc))

    # Concatenate transcript entries into a single string.
    text = " ".join(entry.get("text", "") for entry in transcript_list)
    # Extract language if present in the first entry.
    language = transcript_list[0].get("language") if transcript_list else None

    response = {
        "videoId": videoId,
        "text": text,
        "source": "youtube_transcript_api",
    }
    if language:
        response["language"] = language
    return response
