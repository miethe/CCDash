import json
import time
import unittest

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from backend.adapters.auth.bearer import RequestAuthenticationError, StaticBearerTokenIdentityProvider
from backend.adapters.auth.local import LocalIdentityProvider
from backend.adapters.auth.provider_factory import (
    HostedBearerTokenIdentityProvider,
    create_auth_identity_provider,
)
from backend.adapters.auth.providers import (
    ClerkJWTProvider,
    ClerkJWTProviderSettings,
    GenericOIDCProvider,
    HostedAuthValidationContext,
    OIDCProviderSettings,
)
from backend.application.context import RequestMetadata
from backend.config import AuthProviderConfig


ISSUER = "https://issuer.example.test"
AUDIENCE = "ccdash-api"
JWKS_URL = "https://issuer.example.test/.well-known/jwks.json"


class _KeyPair:
    def __init__(self, kid: str = "kid-1") -> None:
        self.kid = kid
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.private_pem = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self.public_pem = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    @property
    def jwk(self) -> dict:
        jwk = json.loads(RSAAlgorithm.to_jwk(self.private_key.public_key()))
        jwk.update({"kid": self.kid, "use": "sig", "alg": "RS256"})
        return jwk

    @property
    def jwks(self) -> dict:
        return {"keys": [self.jwk]}

    def token(self, **claim_overrides) -> str:
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "sub": "user-123",
            "aud": AUDIENCE,
            "exp": now + 300,
            "iat": now,
            "name": "User One",
            "email": "user@example.test",
            "groups": ["engineering"],
            "roles": ["admin"],
            "scope": "read:project write:project",
            "workspace_id": "workspace-1",
            "project_id": "project-1",
            "enterprise_id": "enterprise-1",
            "team_id": "team-1",
            "nonce": "nonce-1",
            "azp": "https://app.example.test",
        }
        claims.update(claim_overrides)
        return jwt.encode(claims, self.private_pem, algorithm="RS256", headers={"kid": self.kid})


class OIDCProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.keys = _KeyPair()

    def _provider(self, **setting_overrides) -> GenericOIDCProvider:
        settings = {
            "provider_id": "oidc",
            "issuer": ISSUER,
            "audience": AUDIENCE,
            "jwks_url": JWKS_URL,
        }
        settings.update(setting_overrides)

        async def fetch_jwks(url: str):
            self.assertEqual(url, settings.get("jwks_url") or JWKS_URL)
            return self.keys.jwks

        return GenericOIDCProvider(OIDCProviderSettings(**settings), jwks_fetcher=fetch_jwks)

    async def test_oidc_verifies_token_and_maps_claims_to_principal(self) -> None:
        principal = await self._provider().verify(
            self.keys.token(),
            validation_context=HostedAuthValidationContext(
                expected_nonce="nonce-1",
                authorized_party="https://app.example.test",
            ),
        )

        self.assertEqual(principal.subject, "oidc:user-123")
        self.assertEqual(principal.display_name, "User One")
        self.assertEqual(principal.email, "user@example.test")
        self.assertEqual(principal.groups, ("engineering", "admin"))
        self.assertEqual(principal.scopes, ("read:project", "write:project"))
        self.assertEqual(principal.provider.provider_id, "oidc")
        self.assertEqual(principal.provider.issuer, ISSUER)
        self.assertTrue(principal.provider.hosted)
        self.assertEqual(principal.normalized_subject.subject, "user-123")
        self.assertEqual(principal.normalized_subject.stable_id, "oidc:https://issuer.example.test:user:user-123")
        project_membership = next(m for m in principal.memberships if m.scope_type == "project")
        self.assertEqual(project_membership.effective_scope_id, "project-1")
        self.assertEqual(project_membership.enterprise_id, "enterprise-1")
        team_memberships = {m.effective_scope_id for m in principal.memberships if m.scope_type == "team"}
        self.assertIn("team-1", team_memberships)
        self.assertIn("engineering", team_memberships)

    async def test_oidc_discovers_jwks_url_from_issuer(self) -> None:
        async def discovery_fetcher(url: str):
            self.assertEqual(url, f"{ISSUER}/.well-known/openid-configuration")
            return {"issuer": ISSUER, "jwks_uri": JWKS_URL}

        async def jwks_fetcher(url: str):
            self.assertEqual(url, JWKS_URL)
            return self.keys.jwks

        provider = GenericOIDCProvider(
            OIDCProviderSettings(provider_id="oidc", issuer=ISSUER, audience=AUDIENCE),
            discovery_fetcher=discovery_fetcher,
            jwks_fetcher=jwks_fetcher,
        )

        principal = await provider.verify(self.keys.token())
        self.assertEqual(principal.subject, "oidc:user-123")

    async def test_oidc_rejects_missing_metadata_and_missing_token(self) -> None:
        with self.assertRaises(RequestAuthenticationError) as missing_metadata:
            await self._provider(issuer="").verify(self.keys.token())
        self.assertEqual(missing_metadata.exception.status_code, 503)

        with self.assertRaises(RequestAuthenticationError) as missing_token:
            await self._provider().verify("")
        self.assertEqual(missing_token.exception.status_code, 401)

    async def test_oidc_rejects_invalid_signature_issuer_audience_and_missing_subject(self) -> None:
        wrong_signing_key = _KeyPair(kid=self.keys.kid)
        cases = (
            wrong_signing_key.token(),
            self.keys.token(iss="https://wrong.example.test"),
            self.keys.token(aud="wrong-audience"),
            self.keys.token(sub=None),
        )
        for token in cases:
            with self.subTest(token=token[-16:]):
                with self.assertRaises(RequestAuthenticationError) as ctx:
                    await self._provider().verify(token)
                self.assertEqual(ctx.exception.status_code, 401)

    async def test_oidc_rejects_nonce_state_and_authorized_party_mismatches(self) -> None:
        provider = self._provider(allowed_authorized_parties=("https://app.example.test",))
        token = self.keys.token()
        contexts = (
            HostedAuthValidationContext(expected_nonce="wrong"),
            HostedAuthValidationContext(expected_state="state-1", presented_state="wrong"),
            HostedAuthValidationContext(authorized_party="https://wrong.example.test"),
        )
        for context in contexts:
            with self.subTest(context=context):
                with self.assertRaises(RequestAuthenticationError) as ctx:
                    await provider.verify(token, validation_context=context)
                self.assertEqual(ctx.exception.status_code, 401)

        with self.assertRaises(RequestAuthenticationError) as azp_ctx:
            await provider.verify(self.keys.token(azp="https://wrong.example.test"))
        self.assertEqual(azp_ctx.exception.status_code, 401)

    async def test_oidc_refreshes_jwks_when_kid_is_not_cached(self) -> None:
        calls = 0
        stale_key = _KeyPair("stale-kid")

        async def fetch_jwks(url: str):
            nonlocal calls
            self.assertEqual(url, JWKS_URL)
            calls += 1
            return stale_key.jwks if calls == 1 else self.keys.jwks

        provider = GenericOIDCProvider(
            OIDCProviderSettings(provider_id="oidc", issuer=ISSUER, audience=AUDIENCE, jwks_url=JWKS_URL),
            jwks_fetcher=fetch_jwks,
        )

        principal = await provider.verify(self.keys.token())
        self.assertEqual(principal.subject, "oidc:user-123")
        self.assertEqual(calls, 2)


class ClerkProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_clerk_provider_verifies_public_key_and_authorized_party(self) -> None:
        keys = _KeyPair()
        provider = ClerkJWTProvider(
            ClerkJWTProviderSettings(
                jwt_key=keys.public_pem.decode("utf-8"),
                audience=AUDIENCE,
                allowed_authorized_parties=("https://app.example.test",),
            )
        )

        principal = await provider.verify(keys.token())
        self.assertEqual(principal.subject, "clerk:user-123")
        self.assertEqual(principal.provider.provider_id, "clerk")
        self.assertEqual(principal.provider.issuer, ISSUER)

        with self.assertRaises(RequestAuthenticationError):
            await provider.verify(keys.token(azp="https://wrong.example.test"))


class AuthProviderFactoryTests(unittest.IsolatedAsyncioTestCase):
    def _config(self, provider: str, **overrides) -> AuthProviderConfig:
        values = {
            "provider": provider,
            "runtime_profile": "api",
            "deployment_mode": "hosted",
            "oidc_issuer": ISSUER,
            "oidc_audience": AUDIENCE,
            "oidc_jwks_url": JWKS_URL,
            "clerk_publishable_key": "pk_test_example",
            "clerk_secret_key": "sk_test_example",
            "clerk_jwt_key": "public-key",
        }
        values.update(overrides)
        return AuthProviderConfig(**values)

    async def test_factory_selects_configured_provider(self) -> None:
        self.assertIsInstance(create_auth_identity_provider(self._config("local")), LocalIdentityProvider)
        self.assertIsInstance(
            create_auth_identity_provider(self._config("static_bearer")),
            StaticBearerTokenIdentityProvider,
        )
        self.assertIsInstance(
            create_auth_identity_provider(self._config("oidc")),
            HostedBearerTokenIdentityProvider,
        )
        self.assertIsInstance(
            create_auth_identity_provider(self._config("clerk")),
            HostedBearerTokenIdentityProvider,
        )

    async def test_hosted_identity_provider_extracts_bearer_token(self) -> None:
        keys = _KeyPair()

        async def fetch_jwks(url: str):
            return keys.jwks

        identity_provider = HostedBearerTokenIdentityProvider(
            GenericOIDCProvider(
                OIDCProviderSettings(provider_id="oidc", issuer=ISSUER, audience=AUDIENCE, jwks_url=JWKS_URL),
                jwks_fetcher=fetch_jwks,
            )
        )
        principal = await identity_provider.get_principal(
            RequestMetadata(
                headers={"authorization": f"Bearer {keys.token()}"},
                method="GET",
                path="/api/v1/projects",
            ),
            runtime_profile="api",
        )
        self.assertEqual(principal.subject, "oidc:user-123")


if __name__ == "__main__":
    unittest.main()
