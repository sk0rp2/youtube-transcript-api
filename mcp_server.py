"""Optional OAuth-protected MCP resource server; no authorization server is embedded."""

import os
from dataclasses import dataclass
from urllib.parse import urlsplit
from typing import Any

import jwt
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import AnyHttpUrl
from starlette.concurrency import run_in_threadpool

SCOPE = "transcripts:read"


def https_url(value: str, name: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise ValueError(f"{name} must be an absolute HTTPS URL without credentials, query or fragment")
    return value


@dataclass(frozen=True)
class OAuthConfig:
    issuer: str
    jwks_url: str
    resource: str
    subjects: frozenset[str]

    @classmethod
    def from_env(cls):
        issuer = https_url(os.environ.get("MCP_OAUTH_ISSUER", ""), "MCP_OAUTH_ISSUER")
        jwks = https_url(os.environ.get("MCP_OAUTH_JWKS_URL", ""), "MCP_OAUTH_JWKS_URL")
        resource = https_url(os.environ.get("MCP_RESOURCE_URL", ""), "MCP_RESOURCE_URL")
        if urlsplit(resource).path != "/mcp":
            raise ValueError("MCP_RESOURCE_URL must end in /mcp (no trailing slash)")
        subjects = frozenset(s.strip() for s in os.environ.get("MCP_ALLOWED_SUBJECTS", "").split(",") if s.strip())
        if not subjects:
            raise ValueError("MCP_ALLOWED_SUBJECTS must explicitly allow at least one OAuth subject")
        return cls(issuer, jwks, resource, subjects)


class OAuthTokenVerifier:
    def __init__(self, config: OAuthConfig):
        self.config = config
        # Only this administrator-configured URL is used; never a token's jku/x5u.
        self.jwks = jwt.PyJWKClient(config.jwks_url, cache_jwk_set=True, lifespan=300, timeout=5)

    def _verify(self, token: str) -> AccessToken | None:
        try:
            signing_key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token, signing_key.key, algorithms=["RS256"],
                issuer=self.config.issuer, audience=self.config.resource,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
            if claims["sub"] not in self.config.subjects:
                return None
            scope = claims.get("scope", "")
            if not isinstance(scope, str):
                return None
            return AccessToken(
                token=token, client_id=str(claims.get("azp", claims["sub"])),
                subject=claims["sub"], scopes=scope.split(),
                expires_at=int(claims["exp"]), resource=self.config.resource,
            )
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            # Never return token contents, provider errors or configuration to clients.
            return None

    async def verify_token(self, token: str) -> AccessToken | None:
        return await run_in_threadpool(self._verify, token)


def build_mcp(config, retrieve_transcript, extract_video_id):
    public_url = urlsplit(config.resource)
    origin = f"{public_url.scheme}://{public_url.netloc}"
    mcp = FastMCP(
        "YouTube Transcript API", stateless_http=True, json_response=True,
        streamable_http_path="/mcp", max_request_body_size=65536,
        token_verifier=OAuthTokenVerifier(config),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(config.issuer), resource_server_url=AnyHttpUrl(config.resource),
            required_scopes=[SCOPE], validate_token_resource=True,
        ),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[public_url.netloc], allowed_origins=[origin],
        ),
    )
    annotations = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
    metadata = {"securitySchemes": [{"type": "oauth2", "scopes": [SCOPE]}]}

    @mcp.tool(annotations=annotations, meta=metadata)
    async def get_transcript(video_id: str) -> dict[str, Any]:
        """Fetch available YouTube subtitles by 11-character video ID. Returns text and language, not a summary."""
        from fastapi import HTTPException
        try:
            return await run_in_threadpool(retrieve_transcript, video_id)
        except HTTPException as exc:
            raise ToolError(exc.detail) from None

    @mcp.tool(annotations=annotations, meta=metadata)
    async def get_transcript_from_url(url: str) -> dict[str, Any]:
        """Fetch available subtitles from a YouTube watch, short, live or youtu.be URL."""
        video_id = extract_video_id(url)
        if not video_id:
            raise ToolError("Invalid YouTube URL")
        return await get_transcript(video_id)

    @mcp.tool(annotations=annotations, meta=metadata)
    async def extract_video_id_from_url(url: str) -> dict[str, Any]:
        """Extract the video ID from a supported YouTube URL without fetching it."""
        video_id = extract_video_id(url)
        if not video_id:
            raise ToolError("Invalid YouTube URL")
        return {"videoId": video_id}

    return mcp
