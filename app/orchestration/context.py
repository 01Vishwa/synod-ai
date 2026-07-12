"""
orchestration/context.py — Graph execution dependencies.

LangGraph node functions receive the `state` dict. To avoid global singletons
and to keep the architecture purely dependency-injected, we pass our adapters
(Vault, Tracer, Repository) down via LangChain's RunnableConfig.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.adapters.security.key_vault import KeyVault
from app.domain.ports.observability_port import SpanContext, TracerPort
from app.domain.ports.session_repository import SessionRepository


@dataclass
class GraphDependencies:
    """
    Injected into every LangGraph node via config["configurable"]["deps"].
    """
    vault: KeyVault
    tracer: TracerPort
    repository: SessionRepository
    root_span: SpanContext

    # Because a LangGraph run happens asynchronously in the background,
    # it must look up its own API keys (from the DB) using the user_id
    # embedded in the CouncilState.
    db_session_factory: Any  # async_sessionmaker[AsyncSession]


def get_deps(config: dict) -> GraphDependencies:
    """Extract dependencies from a LangGraph RunnableConfig."""
    deps = config.get("configurable", {}).get("deps")
    if not isinstance(deps, GraphDependencies):
        raise RuntimeError("GraphDependencies not found in config['configurable']['deps']")
    return deps
