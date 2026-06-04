"""
AI WealthPilot - Shared Utility Functions
AI WealthPilot - 共享工具函数

Provides common utility functions used across multiple modules
to ensure consistency and prevent code duplication.

提供跨模块使用的公共工具函数，确保一致性并防止代码重复。
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
    # 将所有非单词字符和非连字符替换为下划线
    sanitized = re.sub(r'[^\w\-]', '_', name).lower()
    # Collapse consecutive underscores / 合并连续下划线
    sanitized = re.sub(r'_+', '_', sanitized).strip('_')
    return sanitized or "unnamed"
