import json
import math
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from typesafe_client import TypeSafeError, build_request, evaluate

DEFAULT_INSTRUCTIONS = "Answer the yes-or-no question in the state using the supplied context."


class YesNoTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        instructions = tool_parameters.get("instructions", DEFAULT_INSTRUCTIONS)
        if not isinstance(instructions, str) or not instructions.strip():
            raise TypeSafeError("instructions must be a nonempty string.")

        threshold = tool_parameters.get("threshold", 0.5)
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, int | float)
            or not math.isfinite(threshold)
            or not 0 <= threshold <= 1
        ):
            raise TypeSafeError("threshold must be a number between 0 and 1.")

        criteria = {}
        for parameter, option in (("yes_criteria", "true"), ("no_criteria", "false")):
            value = tool_parameters.get(parameter)
            if value is None or value == "":
                continue
            if not isinstance(value, str):
                raise TypeSafeError(f"{parameter} must be a string.")
            if value.strip():
                criteria[option] = value

        question = {"type": "noul", "instructions": instructions}
        if criteria:
            question["criteria"] = criteria
        parameters = {
            "state": tool_parameters.get("state"),
            "questions": json.dumps({"decision": question}),
        }
        if "model" in tool_parameters:
            parameters["model"] = tool_parameters["model"]
        result = evaluate(self.runtime.credentials.get("api_key"), build_request(parameters))
        probability = result["answers"]["decision"]["noul"]
        decision = probability >= threshold

        yield self.create_json_message(result)
        yield self.create_variable_message("probability", probability)
        yield self.create_variable_message("decision", decision)
        yield self.create_variable_message("model", result["model"])
        yield self.create_variable_message("usage", result["usage"])
        yield self.create_text_message("Yes" if decision else "No")
