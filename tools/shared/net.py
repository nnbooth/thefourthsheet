"""net.py — download over HTTPS with a trusted certificate list on every machine.

Python from python.org on a Mac has no certificate list of its own until "Install Certificates" is run, so secure
downloads fail there. certifi (in requirements.txt) supplies one; the system's own list is used if it's missing.
"""

import ssl
import urllib.request


def _context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def urlopen(url_or_request, timeout=15):
    return urllib.request.urlopen(url_or_request, timeout=timeout, context=_context())
