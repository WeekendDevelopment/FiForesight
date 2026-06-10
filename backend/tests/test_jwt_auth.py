"""
JWT verification tests for get_user_id — covers both Supabase signing schemes:
  - ES256 (asymmetric, verified via JWKS public key) — the default for projects
    with JWT signing keys, and the case that previously failed (HS256-only decode
    rejected every ES256 token, 401-ing all authed endpoints after sign-in).
  - HS256 (legacy shared secret).
"""
import importlib as _il

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

_deps = _il.import_module("dependencies")

_UUID = "11111111-1111-4111-8111-111111111111"


def _es256_token(
    private_key: ec.EllipticCurvePrivateKey, sub: str = _UUID, kid: str = "test-kid"
) -> str:
    return jwt.encode(
        {"sub": sub, "aud": "authenticated"},
        private_key,
        algorithm="ES256",
        headers={"kid": kid},
    )


class _FakeSigningKey:
    def __init__(self, key: object) -> None:
        self.key = key


class _FakeJWKSClient:
    """Stand-in for PyJWKClient that returns a fixed public key."""
    def __init__(self, public_key: object) -> None:
        self._public_key = public_key

    def get_signing_key_from_jwt(self, _token: str) -> _FakeSigningKey:
        return _FakeSigningKey(self._public_key)


def test_es256_token_verified_via_jwks(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid ES256 token is verified against the JWKS public key → returns sub."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(_deps, "_jwks_client", _FakeJWKSClient(private_key.public_key()))
    token = _es256_token(private_key)
    assert _deps.get_user_id(f"Bearer {token}") == _UUID


def test_es256_token_wrong_key_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """An ES256 token signed by a different key fails verification → ''."""
    signer = ec.generate_private_key(ec.SECP256R1())
    other = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(_deps, "_jwks_client", _FakeJWKSClient(other.public_key()))
    token = _es256_token(signer)
    assert _deps.get_user_id(f"Bearer {token}") == ""


def test_es256_token_without_jwks_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """An ES256 token with no JWKS client configured can't be verified → ''."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(_deps, "_jwks_client", None)
    monkeypatch.setattr(_deps.Config, "ALLOW_INSECURE_JWT", False)
    token = _es256_token(private_key)
    assert _deps.get_user_id(f"Bearer {token}") == ""


def test_hs256_token_still_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    """Legacy HS256 path keeps working when a shared secret is configured."""
    secret = "test-hs256-secret"
    monkeypatch.setattr(_deps, "_jwks_client", None)
    monkeypatch.setattr(_deps.Config, "SUPABASE_JWT_SECRET", secret)
    token = jwt.encode({"sub": _UUID, "aud": "authenticated"}, secret, algorithm="HS256")
    assert _deps.get_user_id(f"Bearer {token}") == _UUID


def test_non_bearer_returns_empty() -> None:
    assert _deps.get_user_id("") == ""
    assert _deps.get_user_id("Basic abc") == ""
