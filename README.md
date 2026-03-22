# YouTube Transcript API

Simple FastAPI application to fetch YouTube transcripts for a given video ID and provide basic health and video ID extraction endpoints.

## Features

- `GET /health` returns `{ "status": "ok" }` to verify the service is running.
- `GET /extract-video-id?url=<youtube_url>` extracts a YouTube video ID from common URL formats such as `youtu.be`, `watch`, `embed`, `shorts`, and `live`.
- `GET /transcript?videoId=<id>` fetches the transcript for the specified YouTube video using `youtube-transcript-api` and returns JSON.

## Requirements

- Python 3.14
- Dependencies listed in `requirements.txt` (`fastapi`, `uvicorn`, `youtube-transcript-api`, `python-dotenv`)

## Running locally

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Create a `.env` file in the project root with your API key:
   ```env
   API_KEY=your-secret-key
   ```
   The application loads this file automatically via `python-dotenv`.
3. Start the server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```
4. Access the API locally at `http://localhost:8000`.

## Deployment

This repository includes a `Procfile` and `runtime.txt` for easy deployment to platforms like Northflank, Render or Fly.io. Set the environment variable `API_KEY` in the platform's configuration to secure your endpoints.

## Endpoints

- **`/health`** - health check endpoint, returns `{"status": "ok"}`.
- **`/extract-video-id`** - accepts a `url` query parameter and returns the extracted `videoId`.
- **`/transcript`** - accepts a `videoId` query parameter and returns the transcript for the video. Requires the `X-API-Key` header with the correct key.

## Verification

Run the basic verification suite with:

```bash
python -m unittest discover -s tests
```
