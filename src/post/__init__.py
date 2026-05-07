"""Post-processors translating motion IR programs into vendor-specific source.

Public API:

* :class:`Post` — Protocol every post-processor implements.
* :class:`RAPIDPost` — emits ABB RAPID ``.mod`` source.
"""

from src.post.abb_rapid import RAPIDPost
from src.post.base import Post

__all__ = ["Post", "RAPIDPost"]
