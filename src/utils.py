"""
AI WealthPilot - Shared Utility Functions

Provides common utility functions used across multiple modules
to ensure consistency and prevent code duplication.
"""

import re


def sanitize_filename(name: str) -> str:
    """
    Sanitize a user-provided string for safe use as a filename component.

    Strips all characters except word characters (letters, digits, underscore)
    and hyphens. This prevents directory traversal and special character injection.

    Args:
        name: Raw user input string.

    Returns:
        Sanitized string safe for use in filenames.
    """
    if not name:
        return "unnamed"
    # Replace any non-word, non-hyphen character with underscore
    sanitized = re.sub(r'[^\w\-]', '_', name).lower()
    # Collapse consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized).strip('_')
    return sanitized or "unnamed"
