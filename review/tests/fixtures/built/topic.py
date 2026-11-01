"""A tiny tutor for the review page's tests."""

def double(x):
    """Twice x."""
    return 2 * x


TOOLS = []
PLOTS = {"line": "A straight line."}
PLOT_PARAMS = {}


def run(name, args, state):
    raise ValueError(name)


def make_plot(args):
    return "ok", {"plot": {"data": [], "layout": {}}}
