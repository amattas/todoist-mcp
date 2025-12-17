"""Todoist API constants and validation sets."""

# Valid Todoist colors (as frozenset for O(1) membership testing)
VALID_COLORS = frozenset(
    [
        "berry_red",
        "red",
        "orange",
        "yellow",
        "olive_green",
        "lime_green",
        "green",
        "mint_green",
        "teal",
        "sky_blue",
        "light_blue",
        "blue",
        "grape",
        "violet",
        "lavender",
        "magenta",
        "salmon",
        "charcoal",
        "grey",
        "taupe",
    ]
)

# Valid view styles for projects
VALID_VIEW_STYLES = frozenset(["list", "board"])

# Valid duration units
VALID_DURATION_UNITS = frozenset(["minute", "day"])

# Valid priority values (1-4, where 4 is highest/urgent)
VALID_PRIORITIES = frozenset([1, 2, 3, 4])

# Priority display mappings
PRIORITY_LABELS = {
    4: "Urgent/P1 (red)",
    3: "High/P2 (orange)",
    2: "Medium/P3 (blue)",
    1: "Normal/P4 (gray)",
}

# Color descriptions for documentation
COLOR_DESCRIPTIONS = {
    "berry_red": "Dark red",
    "red": "Red",
    "orange": "Orange",
    "yellow": "Yellow",
    "olive_green": "Olive green",
    "lime_green": "Lime green",
    "green": "Green",
    "mint_green": "Mint green",
    "teal": "Teal",
    "sky_blue": "Sky blue",
    "light_blue": "Light blue",
    "blue": "Blue",
    "grape": "Grape (purple)",
    "violet": "Violet",
    "lavender": "Lavender",
    "magenta": "Magenta",
    "salmon": "Salmon (pink)",
    "charcoal": "Charcoal (dark gray)",
    "grey": "Grey",
    "taupe": "Taupe (brown-gray)",
}
