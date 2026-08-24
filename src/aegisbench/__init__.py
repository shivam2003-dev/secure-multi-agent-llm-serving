"""AegisBench: secure multi-agent LLM serving experiments."""

from aegisbench.config import BenchmarkConfig, ConfigError, load_config

__all__ = ["BenchmarkConfig", "ConfigError", "load_config"]
__version__ = "0.2.0"
