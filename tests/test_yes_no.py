import json

import httpx
import pytest

from tools.yes_no import DEFAULT_INSTRUCTIONS, YesNoTool
from typesafe_client import TypeSafeError


@pytest.mark.parametrize(
    ("probability", "threshold", "decision"),
    [(0.8, 0.5, True), (0.2, 0.5, False), (0.5, 0.5, True), (0.8, 0.9, False), (0, 0, True)],
)
def test_plain_question_and_direct_outputs(mock_http, probability, threshold, decision):
    response = {
        "model": "jev-latest",
        "answers": {"decision": {"type": "noul", "noul": probability}},
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    requests, _ = mock_http(httpx.Response(200, json=response))
    messages = list(
        YesNoTool.from_credentials({"api_key": "secret"}).invoke(
            {
                "state": "Please proceed.",
                "instructions": "Does the user agree?",
                "yes_criteria": "Explicit agreement",
                "no_criteria": "Refusal or uncertainty",
                "threshold": threshold,
            }
        )
    )
    assert json.loads(requests[0].content) == {
        "state": "Please proceed.",
        "model": "jev-latest",
        "questions": {
            "decision": {
                "type": "noul",
                "instructions": "Does the user agree?",
                "criteria": {"true": "Explicit agreement", "false": "Refusal or uncertainty"},
            }
        },
    }
    assert messages[0].message.json_object == response
    outputs = {item.message.variable_name: item.message.variable_value for item in messages[1:-1]}
    assert outputs == {
        "probability": probability,
        "decision": decision,
        "model": "jev-latest",
        "usage": response["usage"],
    }
    assert type(outputs["decision"]) is bool
    assert messages[-1].message.text == ("Yes" if decision else "No")


def test_defaults_and_optional_criteria(mock_http):
    response = {
        "model": "custom-model",
        "answers": {"decision": {"type": "noul", "noul": 1}},
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    requests, _ = mock_http(httpx.Response(200, json=response))
    list(
        YesNoTool.from_credentials({"api_key": "secret"}).invoke(
            {"state": "Is 2 greater than 1?", "yes_criteria": " ", "model": "custom-model"}
        )
    )
    payload = json.loads(requests[0].content)
    assert payload["model"] == "custom-model"
    assert payload["questions"]["decision"] == {
        "type": "noul",
        "instructions": DEFAULT_INSTRUCTIONS,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"instructions": ""},
        {"instructions": None},
        {"threshold": -0.1},
        {"threshold": 1.1},
        {"threshold": True},
        {"threshold": "0.5"},
        {"threshold": float("nan")},
        {"threshold": float("inf")},
        {"yes_criteria": 5},
        {"no_criteria": []},
    ],
)
def test_invalid_parameters_fail_before_request(mock_http, overrides):
    requests, _ = mock_http()
    with pytest.raises(TypeSafeError):
        list(YesNoTool.from_credentials({"api_key": "secret"}).invoke({"state": "x", **overrides}))
    assert not requests
