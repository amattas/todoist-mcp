"""Tests for scripts/verify_auth.py — URL calculation and secret redaction"""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

# Load scripts/verify_auth.py as a module (scripts/ is not a package)
_SPEC = importlib.util.spec_from_file_location(
    "verify_auth", Path(__file__).parent.parent / "scripts" / "verify_auth.py"
)
verify_auth = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(verify_auth)


class TestCalculateMcpUrl:
    def test_hash_matches_server_derivation_with_salt(self):
        result = verify_auth.calculate_mcp_url("my-test-key", "example.com", True, "pepper")
        expected = hashlib.sha256(b"peppermy-test-key").hexdigest()
        assert result["api_key_hash"] == expected
        assert result["endpoints"]["mcp"] == f"https://example.com/app/my-test-key/{expected}/mcp"

    def test_hash_without_salt(self):
        result = verify_auth.calculate_mcp_url("my-test-key", "example.com", True, "")
        assert result["api_key_hash"] == hashlib.sha256(b"my-test-key").hexdigest()
        assert result["md5_salt_used"] is False


class TestRedaction:
    def test_mask_keeps_ends_only(self):
        assert verify_auth._mask("abcdefghijkl") == "abcd...ijkl"

    def test_mask_short_values_fully_hidden(self):
        assert verify_auth._mask("short") == "*****"

    def test_redact_result_masks_key_hash_and_urls(self):
        result = verify_auth.calculate_mcp_url("supersecretapikey123", "example.com", True, "s")
        redacted = verify_auth.redact_result(result)
        assert "supersecretapikey123" not in json.dumps(redacted)
        assert result["api_key_hash"] not in json.dumps(redacted)
        # Health endpoint has no secrets and must survive untouched
        assert redacted["endpoints"]["health"] == result["endpoints"]["health"]

    def test_redact_result_does_not_mutate_input(self):
        result = verify_auth.calculate_mcp_url("supersecretapikey123", "example.com", True, "s")
        verify_auth.redact_result(result)
        assert result["api_key"] == "supersecretapikey123"


class TestMainOutput:
    def _run_main(self, argv, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["verify_auth.py", *argv])
        monkeypatch.delenv("MCP_API_KEY", raising=False)
        monkeypatch.delenv("MD5_SALT", raising=False)
        verify_auth.main()
        return capsys.readouterr().out

    def test_default_output_is_redacted(self, capsys, monkeypatch):
        out = self._run_main(["--api-key", "supersecretapikey123"], capsys, monkeypatch)
        assert "supersecretapikey123" not in out
        assert "--show-secrets" in out  # hint for revealing

    def test_show_secrets_reveals_full_url(self, capsys, monkeypatch):
        out = self._run_main(
            ["--api-key", "supersecretapikey123", "--show-secrets"], capsys, monkeypatch
        )
        assert "supersecretapikey123" in out

    def test_json_output_redacted_by_default(self, capsys, monkeypatch):
        out = self._run_main(["--api-key", "supersecretapikey123", "--json"], capsys, monkeypatch)
        assert "supersecretapikey123" not in out
        json.loads(out)  # must still be valid JSON

    def test_json_show_secrets(self, capsys, monkeypatch):
        out = self._run_main(
            ["--api-key", "supersecretapikey123", "--json", "--show-secrets"],
            capsys,
            monkeypatch,
        )
        data = json.loads(out)
        assert data["api_key"] == "supersecretapikey123"

    def test_missing_key_exits_nonzero(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["verify_auth.py"])
        monkeypatch.delenv("MCP_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc:
            verify_auth.main()
        assert exc.value.code == 1
