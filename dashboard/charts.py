# dashboard/charts.py
"""Server-side helpers that shape numbers for the dashboard's small charts."""

SPARK_WIDTH = 100
SPARK_HEIGHT = 32
SPARK_PAD = 4  # keeps the end dot and the 2px line inside the viewBox


def sparkline(values):
    """
    SVG geometry for a small trend line in a 100x32 viewBox.
    Returns {"points": "x,y x,y ...", "end_x", "end_y"} for the template to draw;
    the last value is the current period and gets the accent dot.
    """
    if not values:
        return None
    top = max(values) or 1
    step = (SPARK_WIDTH - 2 * SPARK_PAD) / max(len(values) - 1, 1)
    usable = SPARK_HEIGHT - 2 * SPARK_PAD
    coords = [
        (SPARK_PAD + i * step, SPARK_HEIGHT - SPARK_PAD - (v / top) * usable)
        for i, v in enumerate(values)
    ]
    return {
        "points": " ".join(f"{x:.1f},{y:.1f}" for x, y in coords),
        "end_x": f"{coords[-1][0]:.1f}",
        "end_y": f"{coords[-1][1]:.1f}",
    }


def delta(current, previous):
    """
    Change versus a comparison period, for a stat tile.
    direction is "up", "down" or "flat"; percent is None when there is no base to compare to.
    """
    diff = current - previous
    direction = "up" if diff > 0 else "down" if diff < 0 else "flat"
    percent = round(abs(diff) * 100 / previous) if previous else None
    return {"diff": abs(diff), "direction": direction, "percent": percent}
