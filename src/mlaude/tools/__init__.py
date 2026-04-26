"""Tool discovery package.

All ``tools/*.py`` files that call ``registry.register()`` at module level
are auto-discovered by :func:`registry.discover_builtin_tools`.
"""
