import dify_plugin  # noqa: F401
import httpx
import pytest

import typesafe_client


@pytest.fixture
def mock_http(monkeypatch):
    original_client = httpx.Client
    requests = []
    sleeps = []
    monkeypatch.setattr(typesafe_client.time, "sleep", sleeps.append)
    monkeypatch.setattr(typesafe_client.random, "uniform", lambda *_: 0.25)

    def install(*responses):
        remaining = iter(responses)

        def handler(request):
            requests.append(request)
            response = next(remaining)
            if isinstance(response, Exception):
                raise response
            if callable(response):
                return response(request)
            return response

        monkeypatch.setattr(
            typesafe_client.httpx,
            "Client",
            lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
        )
        return requests, sleeps

    return install


@pytest.fixture
def questions():
    return {
        "urgent": {"type": "noul", "instructions": "Is it urgent?"},
        "team": {
            "type": "choice",
            "instructions": {"task": "Select a team"},
            "criteria": {"ops": "Infrastructure", "other": None},
        },
        "impact": {
            "type": "score",
            "instructions": ["Rate the impact"],
            "criteria": ["Low", "High"],
        },
    }


@pytest.fixture
def result():
    return {
        "model": "jev-latest",
        "answers": {
            "urgent": {"type": "noul", "noul": 0.9},
            "team": {
                "type": "choice",
                "choice": "ops",
                "probabilities": {"ops": 0.8, "other": 0.2},
                "confidence": 0.7,
            },
            "impact": {
                "type": "score",
                "score": 0.8,
                "legend": {"0": "Low", "1": "High"},
                "probabilities": {"0": 0.2, "1": 0.8},
                "confidence": 0.7,
            },
        },
        "usage": {"input_tokens": 30, "output_tokens": 10},
        "future_metadata": "preserved",
    }
