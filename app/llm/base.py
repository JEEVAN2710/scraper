"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class LLMProvider(ABC):
    """Abstract interface for local or cloud LLM providers.

    Allows seamless switching between local Ollama, OpenAI, or other providers
    without modifying application logic.
    """

    @abstractmethod
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text completion for the provided prompt."""
        pass

    @abstractmethod
    def check_availability(self) -> Dict[str, Any]:
        """Check if the LLM backend is reachable and return health metadata."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the active model identifier."""
        pass
