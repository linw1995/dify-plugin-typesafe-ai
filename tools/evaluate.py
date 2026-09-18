from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from typesafe_client import build_request, evaluate


class EvaluateTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        payload = build_request(tool_parameters)
        result = evaluate(self.runtime.credentials.get("api_key"), payload)

        yield self.create_json_message(result)
        for name in ("answers", "model", "usage"):
            yield self.create_variable_message(name, result[name])
