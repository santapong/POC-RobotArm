"""ABB driver package.

Public API:

* :class:`RWSDriver` — online :class:`~src.drivers.Driver` Protocol
  implementation that talks Robot Web Services (RWS) HTTPS+digest auth
  to a real or virtual ABB IRC5 / OmniCore controller.
"""

from src.drivers.abb.rws_client import RWSDriver

__all__ = ["RWSDriver"]
