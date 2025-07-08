from typing import Any

from dify_plugin import ToolProvider


class AgentProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        # todo: validate agents api key
        return