# YouTube Transcript API

Simple FastAPI application to fetch YouTube transcripts for a given video ID and provide basic health and video ID extraction endpoints.

## Features

- `GET /health` returns `{ "status": "ok" }` to verify the service is running.
- `GET /extract-video-id?url=<youtube_url>` extracts a YouTube video ID from common URL formats such as `youtu.be`, `watch`, `embed`, `shorts`, and `live`.
- `GET /transcript?videoId=<id>` fetches the transcript for the specified YouTube video using `youtube-transcript-api` and returns JSON.
- `GET /transcript-from-url?url=<youtube_url>` fetches the transcript directly from a YouTube URL.

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
   TRANSCRIPT_LANGUAGES=pl,en
   ```
   The application loads this file automatically via `python-dotenv`.
   `TRANSCRIPT_LANGUAGES` is optional. When set, the API tries languages in the given order and still prefers manually created subtitles over auto-generated ones for each language.
3. Start the server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```
4. Access the API locally at `http://localhost:8000`.

## Deployment

This repository includes a `Procfile` and `.python-version` for easy deployment to platforms like Northflank, Render or Fly.io. Set the environment variable `API_KEY` in the platform's configuration to secure your endpoints.

## Endpoints

- **`/health`** - health check endpoint, returns `{"status": "ok"}`.
- **`/extract-video-id`** - accepts a `url` query parameter and returns the extracted `videoId`.
- **`/transcript`** - accepts a `videoId` query parameter and returns the transcript for the video. Requires the `X-API-Key` header with the correct key.
- **`/transcript-from-url`** - accepts a YouTube `url` query parameter and returns the transcript for that video. Requires the `X-API-Key` header with the correct key.

## Verification

Run the basic verification suite with:

```bash
python -m unittest discover -s tests
```

## MCP over Streamable HTTP

The same FastAPI process can expose an OAuth-protected `/mcp` endpoint using
`mcp==1.30.0`. REST paths, `X-API-Key`, response fields, language selection and
`/health` remain compatible. Both transports call `retrieve_transcript`; blocking
YouTube requests run in the thread pool. Unexpected upstream exceptions now have
a generic message instead of exposing internals in REST or MCP responses.

MCP is **disabled by default**. Enable it only after configuring these variables:

| Variable | Meaning |
| --- | --- |
| `MCP_ENABLED` | `true` to enable; otherwise MCP is not mounted |
| `MCP_RESOURCE_URL` | Exact external HTTPS URL ending in `/mcp`, no trailing slash |
| `MCP_OAUTH_ISSUER` | Exact HTTPS issuer in the provider's discovery document |
| `MCP_OAUTH_JWKS_URL` | Provider's HTTPS public signing-key endpoint |
| `MCP_ALLOWED_SUBJECTS` | Explicit comma-separated allowlist of provider user `sub` values |

The authorization server is **external**, not included. For ChatGPT, configure an
established OAuth 2.1 provider (for example Auth0) for authorization code + PKCE
S256, client registration or a predefined OAuth client, and resource/audience
`MCP_RESOURCE_URL`. Grant `transcripts:read` only to the intended account. Configure
the callback URL shown by ChatGPT exactly; do not guess or wildcard it. Keep login
and consent at the identity provider. Configure RS256 access tokens with `iss`,
`aud`, `exp`, `iat`, `sub` and a space-separated `scope` claim.

Every MCP transport request requires `Authorization: Bearer <access-token>`.
The server verifies RS256 signatures against the configured JWKS, issuer,
audience, expiry/not-before, subject allowlist and `transcripts:read` scope.
It does not accept REST API keys or query-string tokens for MCP. Missing/invalid
configuration fails startup when enabled. JWKS lookup is cached with a five-second
network timeout. Host and Origin checks use the configured public URL; arbitrary
browser origins are rejected and no permissive CORS policy is installed. Serve
behind Northflank HTTPS and preserve the external Host header. Do not log tokens
or add secrets to the repository or plugin package.

Discovery: `/.well-known/oauth-protected-resource/mcp` (public). Unauthorized MCP
responses advertise it via `WWW-Authenticate`. The provider must separately
publish OAuth/OIDC discovery and handle login, token issuance and refresh.

Tools:

- `get_transcript(video_id)`
- `get_transcript_from_url(url)`
- `extract_video_id_from_url(url)`

The transport is stateless with JSON responses, using Streamable HTTP rather than
the deprecated HTTP+SSE transport. It needs no sticky sessions or shared session
storage. All tools are read-only and return structured data. No audio transcription
or summarization service has been added; missing YouTube captions remain an error.

### Tests

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests
```

Tests exercise actual ASGI HTTP transport, MCP initialization/discovery/tool calls,
OAuth errors using locally signed RSA tokens, metadata, host/origin/body limits,
UTF-8 and REST compatibility. YouTube and JWKS network I/O are mocked; a live
provider/ChatGPT end-to-end test is still required after an approved deployment.
GitHub Actions runs on Python 3.12 and 3.14 without production secrets.

### Northflank rollout (approval required)

1. Inspect the existing service's repository, deployed commit, tracked branch,
   build settings, port, health checks and automatic deployment rules. Do not
   merge or deploy this branch before approval. Check whether PR preview rules
   create additional services/costs.
2. Keep the existing `Procfile` command and public port; `/health` is unchanged.
   Configure OAuth separately, then prepare the variables above. Preserve
   `API_KEY` and `TRANSCRIPT_LANGUAGES`. Do not expose secret values in screenshots.
3. If an isolated preview is authorized, deploy this branch there using a separate
   resource URL and matching OAuth audience. Verify REST, unauthenticated MCP 401,
   metadata, login, tools/list and a real transcript call.
4. After explicit production approval, deploy the reviewed commit and configure
   its production OAuth resource URL. Verify both old REST clients and MCP.
5. Roll back to the previous deployment if necessary. Setting `MCP_ENABLED=false`
   and restarting disables MCP while retaining REST (also requires approval).

### Private ChatGPT plugin after deployment

Use the verified external `/mcp` URL with `type: streamable-http` in the plugin's
`mcp.json`. Configure OAuth using the deployed resource metadata and the provider's
client registration/setup. Do not embed API keys, access tokens or client secrets
in plugin files. A private plugin listing does not replace server authentication.
Connect as an allowlisted subject, verify tools/list and fetch one known video.
Reuse/update the existing YouTube Summary Assistant plugin if it is the intended
integration, rather than creating an accidental duplicate.

References:
- https://developers.openai.com/plugins/build/auth
- https://github.com/modelcontextprotocol/python-sdk

Until the provider is configured and the deployment approved, the private
ChatGPT connection is intentionally pending; a REST API key alone will not enable it.
