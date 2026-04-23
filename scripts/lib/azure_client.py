"""Azure AI Foundry auth + client factory.

Auth priority:
  1. AzureCliCredential (az login) — local/interactive
  2. DefaultAzureCredential — managed identity, env SP, workload identity
  3. API key fallback — AZURE_OPENAI_API_KEY or explicit arg
"""

from __future__ import annotations

import os
import sys

COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
DEFAULT_API_VERSION = "2025-04-01-preview"
DEFAULT_DEPLOYMENT = "gpt-image-2"


def _get_token_provider(verbose: bool = True):
    try:
        from azure.identity import AzureCliCredential, DefaultAzureCredential
    except ImportError:
        return None

    def make_provider(credential):
        def provider():
            return credential.get_token(COGNITIVE_SCOPE).token

        return provider

    try:
        cli = AzureCliCredential()
        cli.get_token(COGNITIVE_SCOPE)
        if verbose:
            print("Auth: Azure CLI credential (az login)")
        return make_provider(cli)
    except Exception:
        pass

    try:
        default = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        default.get_token(COGNITIVE_SCOPE)
        if verbose:
            print("Auth: DefaultAzureCredential (managed identity / service principal)")
        return make_provider(default)
    except Exception:
        return None


def build_client(
    endpoint: str | None = None,
    api_key: str | None = None,
    api_version: str | None = None,
    force_api_key: bool = False,
    verbose: bool = True,
):
    """Return an AzureOpenAI client using the best available auth method."""
    try:
        from openai import AzureOpenAI
    except ImportError:
        print(
            "ERROR: openai package not installed. Run: pip install openai",
            file=sys.stderr,
        )
        sys.exit(1)

    endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
    api_version = api_version or os.environ.get("AZURE_OPENAI_API_VERSION", DEFAULT_API_VERSION)

    if not endpoint:
        print(
            "ERROR: No endpoint. Set AZURE_OPENAI_ENDPOINT or pass endpoint=...",
            file=sys.stderr,
        )
        sys.exit(1)

    if not force_api_key:
        provider = _get_token_provider(verbose=verbose)
        if provider:
            return AzureOpenAI(
                azure_endpoint=endpoint,
                azure_ad_token_provider=provider,
                api_version=api_version,
            )

    if not api_key:
        print(
            "ERROR: No auth available. Either:\n"
            "  - Run 'az login' for CLI auth, or\n"
            "  - Set AZURE_OPENAI_API_KEY for headless/CI auth",
            file=sys.stderr,
        )
        sys.exit(1)

    if verbose:
        print("Auth: API key (headless/CI mode)")
    return AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
    )


def resolve_deployment(cli_value: str | None = None) -> str:
    return cli_value or os.environ.get("AZURE_IMAGE_DEPLOYMENT", DEFAULT_DEPLOYMENT)


def generate_image_bytes(
    client,
    *,
    deployment: str,
    prompt: str,
    size: str = "1024x1024",
    quality: str = "high",
    n: int = 1,
) -> list[bytes]:
    """Generate images and return a list of raw PNG bytes (one per image)."""
    import base64
    import urllib.request

    response = client.images.generate(
        model=deployment,
        prompt=prompt,
        size=size,
        quality=quality,
        n=n,
    )

    out: list[bytes] = []
    for img in response.data:
        if getattr(img, "b64_json", None):
            out.append(base64.b64decode(img.b64_json))
        elif getattr(img, "url", None):
            with urllib.request.urlopen(img.url) as r:
                out.append(r.read())
        else:
            raise RuntimeError(f"No image data in response item: {img}")
    return out
