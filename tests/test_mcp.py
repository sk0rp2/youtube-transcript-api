import importlib
import os
import time
import unittest
from unittest.mock import Mock, patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from youtube_transcript_api import CouldNotRetrieveTranscript

import main
from mcp_server import OAuthConfig, OAuthTokenVerifier

RESOURCE = "https://transcripts.example.com/mcp"
ISSUER = "https://auth.example.com/"
SUBJECT = "test-user"
ENV = {
    "MCP_ENABLED": "true", "MCP_OAUTH_ISSUER": ISSUER,
    "MCP_OAUTH_JWKS_URL": ISSUER + ".well-known/jwks.json",
    "MCP_RESOURCE_URL": RESOURCE, "MCP_ALLOWED_SUBJECTS": SUBJECT,
    "API_KEY": "rest-test-key",
}


class MCPTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.env = patch.dict(os.environ, ENV)
        self.env.start()
        importlib.reload(main)
        self.keys = patch.object(main.mcp._token_verifier.jwks, "get_signing_key_from_jwt", return_value=Mock(key=self.key.public_key()))
        self.keys.start()
        self.client = TestClient(main.app, base_url="https://transcripts.example.com")
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.keys.stop()
        self.env.stop()
        importlib.reload(main)

    def token(self, **overrides):
        now = int(time.time())
        claims = dict(iss=ISSUER, aud=RESOURCE, sub=SUBJECT, iat=now, exp=now+300, scope="transcripts:read")
        claims.update(overrides)
        return jwt.encode(claims, self.key, algorithm="RS256")

    def rpc(self, method, params=None, token=None, **headers):
        return self.client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            headers={"Accept": "application/json, text/event-stream", "Authorization": "Bearer " + (token or self.token()), **headers})

    def test_initialize_list_and_call(self):
        response = self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
        self.assertEqual(response.status_code, 200)
        self.assertIn("serverInfo", response.json()["result"])
        tools = self.rpc("tools/list").json()["result"]["tools"]
        self.assertEqual({t["name"] for t in tools}, {"get_transcript", "get_transcript_from_url", "extract_video_id_from_url"})
        self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in tools))
        transcript = Mock(language="Polish")
        transcript.to_raw_data.return_value = [{"text": "Zażółć gęślą jaźń"}]
        with patch("main.fetch_best_transcript", return_value=transcript) as fetch:
            for name, arguments in [("get_transcript", {"video_id": "dQw4w9WgXcQ"}), ("get_transcript_from_url", {"url": "https://youtu.be/dQw4w9WgXcQ"})]:
                result = self.rpc("tools/call", {"name": name, "arguments": arguments}).json()["result"]
                self.assertFalse(result.get("isError"))
                self.assertEqual(result["structuredContent"]["text"], "Zażółć gęślą jaźń")
            self.assertEqual(fetch.call_count, 2)
        result = self.rpc("tools/call", {"name": "extract_video_id_from_url", "arguments": {"url": "https://youtu.be/dQw4w9WgXcQ"}}).json()["result"]
        self.assertEqual(result["structuredContent"], {"videoId": "dQw4w9WgXcQ"})

    def test_authentication_on_all_transport_methods(self):
        for method in ("GET", "POST", "DELETE"):
            for headers in ({}, {"X-API-Key": ENV["API_KEY"]}, {"Authorization": "Bearer nonsense"}):
                response = self.client.request(method, "/mcp", headers=headers)
                self.assertEqual(response.status_code, 401)
                self.assertIn("resource_metadata", response.headers["www-authenticate"])
        self.assertEqual(self.client.post("/mcp?access_token=" + self.token()).status_code, 401)

    def test_invalid_tokens_and_scope(self):
        for claims in ({"exp": 1}, {"aud": "another-service"}, {"iss": "https://evil.example/"}, {"sub": "other-user"}, {"nbf": int(time.time())+300}):
            with self.subTest(claims=claims):
                self.assertEqual(self.rpc("tools/list", token=self.token(**claims)).status_code, 401)
        self.assertEqual(self.rpc("tools/list", token=self.token(scope="other:read")).status_code, 403)
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        claims = jwt.decode(self.token(), options={"verify_signature": False})
        forged = jwt.encode(claims, other, algorithm="RS256")
        self.assertEqual(self.rpc("tools/list", token=forged).status_code, 401)
        del claims["exp"]
        self.assertEqual(self.rpc("tools/list", token=jwt.encode(claims, self.key, algorithm="RS256")).status_code, 401)

    def test_origin_host_and_size_checks(self):
        self.assertEqual(self.rpc("tools/list", Origin="https://evil.example").status_code, 403)
        self.assertEqual(self.rpc("tools/list", Host="evil.example").status_code, 421)
        self.assertEqual(self.rpc("tools/list", {"padding": "x"*70000}).status_code, 413)

    def test_discovery_metadata(self):
        response = self.client.get("/.well-known/oauth-protected-resource/mcp")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["resource"], RESOURCE)
        self.assertEqual(response.json()["authorization_servers"], [ISSUER])
        self.assertEqual(response.json()["scopes_supported"], ["transcripts:read"])

    def test_tool_errors_are_safe(self):
        with patch("main.fetch_best_transcript") as fetch:
            for name, args in [("get_transcript", {"video_id": "invalid"}), ("get_transcript_from_url", {"url": "https://evil.example"})]:
                result = self.rpc("tools/call", {"name": name, "arguments": args}).json()["result"]
                self.assertTrue(result["isError"])
            fetch.assert_not_called()
        for error, expected in [(CouldNotRetrieveTranscript("dQw4w9WgXcQ"), "Transcript not available"), (RuntimeError("SECRET_INTERNAL_DATA"), "Unexpected error")]:
            with patch("main.fetch_best_transcript", side_effect=error):
                response = self.rpc("tools/call", {"name": "get_transcript", "arguments": {"video_id": "dQw4w9WgXcQ"}})
                self.assertTrue(response.json()["result"]["isError"])
                self.assertIn(expected, response.text)
                self.assertNotIn("SECRET_INTERNAL_DATA", response.text)

    def test_rest_compatibility(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/transcript", params={"videoId": "dQw4w9WgXcQ"}).status_code, 401)
        transcript = Mock(language="Polish")
        transcript.to_raw_data.return_value = [{"text": "Cześć"}]
        with patch("main.fetch_best_transcript", return_value=transcript):
            for path, params in [("/transcript", {"videoId": "dQw4w9WgXcQ"}), ("/transcript-from-url", {"url": "https://youtu.be/dQw4w9WgXcQ"})]:
                response = self.client.get(path, params=params, headers={"X-API-Key": ENV["API_KEY"]})
                self.assertEqual(response.status_code, 200)
                self.assertIn("charset=utf-8", response.headers["content-type"])
                self.assertEqual(response.json()["text"], "Cześć")
        self.assertEqual(self.client.get("/openapi.json").status_code, 200)


class ConfigurationTestCase(unittest.TestCase):
    def test_enabled_requires_complete_secure_configuration(self):
        for field in ("MCP_OAUTH_ISSUER", "MCP_OAUTH_JWKS_URL", "MCP_RESOURCE_URL", "MCP_ALLOWED_SUBJECTS"):
            with patch.dict(os.environ, {**ENV, field: ""}):
                with self.assertRaises(ValueError):
                    OAuthConfig.from_env()
        with patch.dict(os.environ, {**ENV, "MCP_RESOURCE_URL": "http://example.com/mcp"}):
            with self.assertRaises(ValueError):
                OAuthConfig.from_env()

    def test_disabled_rest_remains_available(self):
        with patch.dict(os.environ, {"MCP_ENABLED": "false"}):
            importlib.reload(main)
            with TestClient(main.app) as client:
                self.assertEqual(client.post("/mcp").status_code, 404)
                self.assertEqual(client.get("/health").status_code, 200)
        importlib.reload(main)
