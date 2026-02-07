"""Web UI components."""

# Lazy import to avoid Streamlit dependency issues
__all__ = ["vis_network_graph", "create_spine_graph_data"]


def __getattr__(name):
    """Lazy import vis_network components."""
    if name in ("vis_network_graph", "create_spine_graph_data"):
        from .vis_network import vis_network_graph, create_spine_graph_data
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
