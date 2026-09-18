import json
import random
import time
from typing import Annotated, Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

API_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"
MAX_ATTEMPTS = 3


class TypeSafeError(Exception):
    """An actionable error that is safe to expose through Dify."""


class Question(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)
    instructions: str | dict[str, JsonValue] | list[JsonValue]


class NoulQuestion(Question):
    type: Literal["noul"]
    criteria: dict[Literal["true", "false"], str] = Field(default_factory=dict)


class ChoiceQuestion(Question):
    type: Literal["choice"]
    criteria: dict[str, str | None] = Field(min_length=1)


class ScoreQuestion(Question):
    type: Literal["score"]
    criteria: list[str] = Field(min_length=2)


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)
    state: str | dict[str, JsonValue] | list[JsonValue]
    model: str = Field(min_length=1)
    questions: dict[
        str, Annotated[NoulQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="type")]
    ] = Field(min_length=1)


Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class Answer(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow", allow_inf_nan=False)


class NoulAnswer(Answer):
    type: Literal["noul"]
    noul: Probability


class ChoiceAnswer(Answer):
    type: Literal["choice"]
    choice: str
    probabilities: dict[str, Probability]
    confidence: Probability


class ScoreAnswer(Answer):
    type: Literal["score"]
    score: float
    legend: dict[str, str]
    probabilities: dict[str, Probability]
    confidence: Probability


class Usage(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow")
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow")
    model: str
    answers: dict[
        str, Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")]
    ]
    usage: Usage


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON number")


def _parse_json(value: Any, name: str) -> Any:
    if not isinstance(value, str):
        raise TypeSafeError(f"{name} must be a JSON string.")
    try:
        return json.loads(value, parse_constant=_reject_constant)
    except ValueError:
        raise TypeSafeError(f"{name} must contain valid JSON with finite numbers.") from None


def build_request(parameters: dict[str, Any]) -> dict[str, Any]:
    state_format = parameters.get("state_format", "text")
    state = parameters.get("state")
    if state_format == "json":
        state = _parse_json(state, "state")
    elif state_format != "text":
        raise TypeSafeError("state_format must be text or json.")
    elif not isinstance(state, str):
        raise TypeSafeError("state must be a string in text mode.")

    try:
        request = EvaluationRequest.model_validate(
            {
                "state": state,
                "model": parameters.get("model", DEFAULT_MODEL),
                "questions": _parse_json(parameters.get("questions"), "questions"),
            }
        )
    except ValidationError as exc:
        # Validation errors normally include user content; expose only the field and reason.
        error = exc.errors(include_input=False, include_url=False)[0]
        location = ".".join(str(part) for part in error["loc"])
        raise TypeSafeError(f"Invalid request at {location}: {error['msg']}") from None
    if not request.model.strip():
        raise TypeSafeError("model must not be blank.")
    return request.model_dump(exclude_unset=True)


def evaluate(api_key: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(api_key, str) or not api_key.strip():
        raise TypeSafeError("Configure a TypeSafe API key in the provider credentials.")
    key = api_key.strip()
    if any(ord(character) < 33 or ord(character) > 126 for character in key):
        raise TypeSafeError("The TypeSafe API key contains invalid characters.")

    # Only retry explicit rejection responses; transport failures may have consumed credits.
    with httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0), follow_redirects=False) as client:
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = client.post(
                    API_URL,
                    headers={"Authorization": f"Bearer {key}"},
                    json=payload,
                )
            except httpx.TimeoutException:
                raise TypeSafeError("TypeSafe timed out. Try again later.") from None
            except httpx.RequestError:
                raise TypeSafeError("Could not connect to TypeSafe. Try again later.") from None

            if response.status_code in (429, 529) and attempt < MAX_ATTEMPTS - 1:
                time.sleep(2**attempt + random.uniform(0, 0.5))
                continue
            if response.status_code != 200:
                messages = {
                    401: "TypeSafe rejected the API key. Check the provider credentials.",
                    403: "TypeSafe denied access. Check your API key permissions.",
                    422: "TypeSafe rejected the request. Check the model, state, and questions.",
                    429: "TypeSafe rate limit exceeded. Try again later.",
                    529: "TypeSafe is temporarily overloaded. Try again later.",
                }
                # Upstream bodies can echo credentials or state, so never include them in errors.
                raise TypeSafeError(
                    messages.get(
                        response.status_code, f"TypeSafe returned HTTP {response.status_code}."
                    )
                )
            try:
                result = response.json()
                parsed = EvaluationResponse.model_validate(result)
                questions = payload["questions"]
                if parsed.answers.keys() != questions.keys() or any(
                    answer.type != questions[name]["type"]
                    for name, answer in parsed.answers.items()
                ):
                    raise ValueError("Mismatched answers")
            except ValueError:
                raise TypeSafeError("TypeSafe returned an invalid evaluation response.") from None
            return result
    raise AssertionError("Unreachable retry state")
