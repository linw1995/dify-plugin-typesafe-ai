import json

import httpx
import pytest
from dify_plugin import DifyPluginEnv
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from provider.typesafe import TypeSafeProvider
from tools.evaluate import EvaluateTool
from typesafe_client import API_URL, TypeSafeError, build_request, evaluate


def test_sdk_registration():
    registration = PluginRegistration(DifyPluginEnv())
    provider, provider_class, tools = registration.tools_mapping["typesafe"]
    assert provider_class.__name__ == "TypeSafeProvider"
    assert provider.credentials_schema[0].name == "api_key"
    assert provider.credentials_schema[0].required
    config, tool_class = tools["evaluate"]
    assert tool_class.__name__ == "EvaluateTool"
    assert set(config.output_schema["properties"]) == {"answers", "model", "usage"}
    answer_schema = config.output_schema["properties"]["answers"]
    assert answer_schema["additionalProperties"]["type"] == "object"
    assert answer_schema["additionalProperties"]["properties"]["noul"]["type"] == "number"
    yes_no_config, yes_no_class = tools["yes_no"]
    assert yes_no_class.__name__ == "YesNoTool"
    assert yes_no_config.output_schema["properties"]["probability"]["type"] == "number"
    assert yes_no_config.output_schema["properties"]["decision"]["type"] == "boolean"


def test_tool_request_and_outputs(mock_http, questions, result):
    requests, sleeps = mock_http(httpx.Response(200, json=result))
    tool = EvaluateTool.from_credentials({"api_key": "  test-secret  "})
    state = '  {"keep": "as text"}  '
    messages = list(tool.invoke({"state": state, "questions": json.dumps(questions)}))
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert str(requests[0].url) == API_URL
    assert requests[0].headers["Authorization"] == "Bearer test-secret"
    assert requests[0].headers["Content-Type"] == "application/json"
    assert requests[0].extensions["timeout"]["connect"] == 5
    assert requests[0].extensions["timeout"]["read"] == 20
    assert json.loads(requests[0].content) == {
        "state": state,
        "model": "jev-latest",
        "questions": questions,
    }
    assert messages[0].message.json_object == result
    assert {
        message.message.variable_name: message.message.variable_value for message in messages[1:]
    } == {key: result[key] for key in ("answers", "model", "usage")}
    assert not sleeps


@pytest.mark.parametrize("state", [{"messages": [{"text": "hello"}]}, ["hello"], "hello"])
def test_structured_state(state, questions):
    payload = build_request(
        {
            "state": json.dumps(state),
            "state_format": "json",
            "questions": json.dumps(questions),
            "model": "custom-model",
        }
    )
    assert payload["state"] == state
    assert payload["model"] == "custom-model"


@pytest.mark.parametrize(
    "overrides",
    [
        {"state": None},
        {"state_format": "auto"},
        {"state_format": "json", "state": "not JSON"},
        {"state_format": "json", "state": "null"},
        {"state_format": "json", "state": "true"},
        {"state_format": "json", "state": "42"},
        {"state_format": "json", "state": '{"x": NaN}'},
        {"state_format": "json", "state": '{"x": 1e999}'},
        {"model": " "},
        {"model": None},
        {"questions": "{}"},
        {"questions": "[]"},
        {"questions": "not JSON"},
        {"questions": '{"x":{"type":"unknown","instructions":"test"}}'},
        {"questions": '{"x":{"type":"noul"}}'},
        {"questions": '{"x":{"type":"noul","instructions":false}}'},
        {"questions": '{"x":{"type":"choice","instructions":"test","criteria":{}}}'},
        {"questions": '{"x":{"type":"score","instructions":"test","criteria":["low"]}}'},
        {"questions": '{"x":{"type":"noul","instructions":"test","criteria":{"yes":"x"}}}'},
    ],
)
def test_invalid_input_never_reaches_api(overrides, mock_http, questions):
    requests, _ = mock_http()
    tool = EvaluateTool.from_credentials({"api_key": "test-secret"})
    with pytest.raises(TypeSafeError):
        list(tool.invoke({"state": "hello", "questions": json.dumps(questions), **overrides}))
    assert not requests


def test_optional_noul_criteria(questions):
    questions["urgent"]["criteria"] = {"true": "Immediate", "false": "Routine"}
    payload = build_request({"state": "hello", "questions": json.dumps(questions)})
    assert payload["questions"] == questions


@pytest.mark.parametrize("key", [None, "", " ", "secret\nheader", "secret key", 123])
def test_invalid_credentials(key, mock_http, questions):
    requests, _ = mock_http()
    with pytest.raises(TypeSafeError, match="key"):
        evaluate(key, {"state": "hello", "questions": questions})
    assert not requests


@pytest.mark.parametrize("status", [401, 403, 422, 500, 302])
def test_http_errors_are_sanitized_and_not_retried(status, mock_http, questions):
    requests, sleeps = mock_http(httpx.Response(status, text="test-secret private-state"))
    with pytest.raises(TypeSafeError) as error:
        evaluate("test-secret", {"state": "private-state", "questions": questions})
    assert "test-secret" not in str(error.value)
    assert "private-state" not in str(error.value)
    assert len(requests) == 1
    assert not sleeps


@pytest.mark.parametrize("status", [429, 529])
def test_retry_backoff_and_success(status, mock_http, questions, result):
    requests, sleeps = mock_http(
        httpx.Response(status), httpx.Response(status), httpx.Response(200, json=result)
    )
    assert evaluate("secret", {"questions": questions}) == result
    assert len(requests) == 3
    assert sleeps == [1.25, 2.25]


@pytest.mark.parametrize("status", [429, 529])
def test_retry_limit(status, mock_http, questions):
    requests, sleeps = mock_http(*(httpx.Response(status) for _ in range(3)))
    with pytest.raises(TypeSafeError):
        evaluate("secret", {"questions": questions})
    assert len(requests) == 3
    assert len(sleeps) == 2


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError])
def test_transport_errors_do_not_retry(error, mock_http, questions):
    requests, sleeps = mock_http(error("secret private-state"))
    with pytest.raises(TypeSafeError) as caught:
        evaluate("secret", {"questions": questions})
    assert "secret" not in str(caught.value)
    assert "private-state" not in str(caught.value)
    assert len(requests) == 1
    assert not sleeps


@pytest.mark.parametrize("body", ["<html>private</html>", "null", "[]", "{}"])
def test_malformed_responses(body, mock_http, questions):
    mock_http(httpx.Response(200, text=body))
    with pytest.raises(TypeSafeError, match="invalid evaluation response"):
        evaluate("secret", {"questions": questions})


@pytest.mark.parametrize("mutation", ["missing", "wrong_type", "invalid_probability", "usage"])
def test_invalid_response_contract(mutation, mock_http, questions, result):
    if mutation == "missing":
        del result["answers"]["urgent"]
    elif mutation == "wrong_type":
        result["answers"]["urgent"] = result["answers"]["team"]
    elif mutation == "invalid_probability":
        result["answers"]["urgent"]["noul"] = 1.5
    else:
        result["usage"]["input_tokens"] = "30"
    mock_http(httpx.Response(200, json=result))
    with pytest.raises(TypeSafeError, match="invalid evaluation response"):
        evaluate("secret", {"questions": questions})


def test_provider_checks_credentials_with_real_request(mock_http):
    requests, _ = mock_http(
        httpx.Response(
            200,
            json={
                "model": "jev-latest",
                "answers": {"check": {"type": "noul", "noul": 1}},
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )
    )
    TypeSafeProvider().validate_credentials({"api_key": "secret"})
    assert json.loads(requests[0].content)["state"] == "Connection check."


def test_provider_wraps_auth_failure(mock_http):
    mock_http(httpx.Response(401, text="secret"))
    with pytest.raises(ToolProviderCredentialValidationError, match="rejected the API key"):
        TypeSafeProvider().validate_credentials({"api_key": "secret"})
