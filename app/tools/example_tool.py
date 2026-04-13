"""
Example: how to add a custom tool to the agent.

Steps:
  1. Define your tool here (or in any file under app/tools/).
  2. Import it in app/tools/registry.py.
  3. Add it to REGISTERED_TOOLS in registry.py.

That's it — the agent graph will pick it up automatically on the next request.
"""

from langchain_core.tools import tool


@tool
def summarize_numbers(numbers: str) -> str:
    """
    Given a comma-separated list of numbers, return basic statistics:
    count, sum, min, max, and average.

    Example input: "10, 20, 30, 40"
    """
    try:
        vals = [float(x.strip()) for x in numbers.split(",") if x.strip()]
        if not vals:
            return "No numbers provided."
        return (
            f"Count: {len(vals)}, "
            f"Sum: {sum(vals):.4g}, "
            f"Min: {min(vals):.4g}, "
            f"Max: {max(vals):.4g}, "
            f"Average: {sum(vals)/len(vals):.4g}"
        )
    except Exception as e:
        return f"Error: {e}"


# To activate this tool, add to registry.py:
#   from app.tools.example_tool import summarize_numbers
#   REGISTERED_TOOLS = [..., summarize_numbers]
