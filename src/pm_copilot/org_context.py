import streamlit as st


def format_org_context() -> str:
    """Format the dynamic org context for prompt injection."""
    ctx = st.session_state.org_context
    if not ctx["company"] and not ctx["public_context"] and not ctx["internal_context"]:
        return "(No organizational context yet. On the first turn, use update_org_context to populate public knowledge about the user's company/domain.)"

    parts = []
    if ctx["company"]:
        parts.append(f"## Organization: {ctx['company']}")
    if ctx["public_context"]:
        parts.append(f"## Public Context\n{ctx['public_context']}")
    if ctx["internal_context"]:
        parts.append(f"## Internal Context (user-provided)\n{ctx['internal_context']}")
    return "\n\n".join(parts)
