"""Post-processors translating motion IR programs into vendor-specific source.

Public API:

* :class:`Post` — Protocol every post-processor implements.
* :class:`RAPIDPost` — emits ABB RAPID ``.mod`` source.
* :class:`KRLPost` — emits paired KUKA KRL ``.src`` + ``.dat`` source.
* :class:`URScriptPost` — emits Universal Robots URScript ``.script`` source.
"""

from src.post.abb_rapid import RAPIDPost
from src.post.base import Post
from src.post.kuka_krl import KRLPost
from src.post.ur_script import URScriptPost

__all__ = ["KRLPost", "Post", "RAPIDPost", "URScriptPost"]
