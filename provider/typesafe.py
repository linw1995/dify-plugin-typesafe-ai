from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from typesafe_client import TypeSafeError, evaluate


class TypeSafeProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            evaluate(
                credentials.get("api_key"),
                {
                    "model": "jev-latest",
                    "state": "Connection check.",
                    "questions": {
                        "check": {"type": "noul", "instructions": "Does the text mention a check?"}
                    },
                },
            )
        except TypeSafeError as exc:
            raise ToolProviderCredentialValidationError(str(exc)) from None
