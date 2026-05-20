"""Tests for AIDetectionModelService ML payload shaping."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.ml_model_service import AIDetectionModelService


@pytest.mark.asyncio
async def test_kazakh_text_is_lowercased_in_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AIDetectionModelService()
    text = "Бұл Мәтін"
    original = text

    response = MagicMock()
    response.json.return_value = {"label": "human", "ai_probability": 0.1}
    response.raise_for_status.return_value = None
    response.aread = AsyncMock(return_value=b"")

    client = MagicMock()
    client.post = AsyncMock(return_value=response)

    monkeypatch.setattr(service, "_client_for", lambda _lang: client)

    try:
        await service.detect_ai_text(text, language="kk")
    finally:
        await service.close()

    _, kwargs = client.post.await_args
    assert kwargs["json"]["text"] == "бұл мәтін"
    assert text == original


@pytest.mark.asyncio
async def test_russian_text_is_not_lowercased_in_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AIDetectionModelService()
    text = "Привет Мир"

    response = MagicMock()
    response.json.return_value = {"label": "human", "ai_probability": 0.1}
    response.raise_for_status.return_value = None
    response.aread = AsyncMock(return_value=b"")

    client = MagicMock()
    client.post = AsyncMock(return_value=response)

    monkeypatch.setattr(service, "_client_for", lambda _lang: client)

    try:
        await service.detect_ai_text(text, language="ru")
    finally:
        await service.close()

    _, kwargs = client.post.await_args
    assert kwargs["json"]["text"] == "Привет Мир"


@pytest.mark.asyncio
async def test_kazakh_lowercasing_does_not_affect_history(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AIDetectionModelService()
    text = "Бұл Мәтін"
    original = text

    response = MagicMock()
    response.json.return_value = {"label": "human", "ai_probability": 0.1}
    response.raise_for_status.return_value = None
    response.aread = AsyncMock(return_value=b"")

    client = MagicMock()
    client.post = AsyncMock(return_value=response)

    monkeypatch.setattr(service, "_client_for", lambda _lang: client)

    try:
        await service.detect_ai_text(text, language="kk")
    finally:
        await service.close()

    assert text == original
    _, kwargs = client.post.await_args
    assert kwargs["json"]["text"] == "бұл мәтін"

