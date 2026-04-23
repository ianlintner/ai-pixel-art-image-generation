"""Provider-neutral image generation wrapper."""

from __future__ import annotations

import os
from dataclasses import dataclass

from lib import azure_client, openai_client

VALID_PROVIDERS = ["auto", "openai", "azure"]


@dataclass(frozen=True)
class ImageGenerator:
    provider: str
    model: str
    client: object


def resolve_provider(cli_value: str | None = None) -> str:
    provider = cli_value or os.environ.get("IMAGE_PROVIDER", "auto")
    if provider != "auto":
        return provider
    if os.environ.get("AZURE_OPENAI_ENDPOINT"):
        return "azure"
    return "openai"


def build_image_generator(
    *,
    provider: str | None = None,
    model: str | None = None,
    azure_endpoint: str | None = None,
    azure_api_key: str | None = None,
    azure_api_version: str | None = None,
    force_azure_api_key: bool = False,
    openai_api_key: str | None = None,
    openai_organization: str | None = None,
) -> ImageGenerator:
    resolved_provider = resolve_provider(provider)

    if resolved_provider == "azure":
        resolved_model = azure_client.resolve_deployment(model)
        return ImageGenerator(
            provider="azure",
            model=resolved_model,
            client=azure_client.build_client(
                endpoint=azure_endpoint,
                api_key=azure_api_key,
                api_version=azure_api_version,
                force_api_key=force_azure_api_key,
            ),
        )

    if resolved_provider == "openai":
        resolved_model = openai_client.resolve_model(model)
        return ImageGenerator(
            provider="openai",
            model=resolved_model,
            client=openai_client.build_client(
                api_key=openai_api_key,
                organization=openai_organization,
            ),
        )

    raise ValueError(f"Unknown image provider: {resolved_provider}")


def generate_image_bytes(
    generator: ImageGenerator,
    *,
    prompt: str,
    size: str = "1024x1024",
    quality: str = "high",
    n: int = 1,
) -> list[bytes]:
    if generator.provider == "azure":
        return azure_client.generate_image_bytes(
            generator.client,
            deployment=generator.model,
            prompt=prompt,
            size=size,
            quality=quality,
            n=n,
        )

    if generator.provider == "openai":
        return openai_client.generate_image_bytes(
            generator.client,
            model=generator.model,
            prompt=prompt,
            size=size,
            quality=quality,
            n=n,
        )

    raise ValueError(f"Unknown image provider: {generator.provider}")
