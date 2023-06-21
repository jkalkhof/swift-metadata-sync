import os

from swift.common.internal_client import InternalClient
from swift.common.wsgi import ConfigString

# see also https://github.com/openstack/swift/blob/master/test/unit/common/test_internal_client.py

"""
    Base class for all classes that implement the sync functionality. Sets up
    the swift client with the default configuration, which points to the local
    Swift configuration. Supplies the skeleton methods that must be overwritten
    by all child classes.
"""
class BaseSync(object):

    INTERNAL_CLIENT_CONFIG = """
[DEFAULT]
[pipeline:main]
pipeline = catch_errors proxy-logging cache proxy-server

[app:proxy-server]
use = egg:swift#proxy

[filter:cache]
use = egg:swift#memcache

[filter:proxy-logging]
use = egg:swift#proxy_logging

[filter:catch_errors]
use = egg:swift#catch_errors
""".lstrip()

    def __init__(self, status_dir, settings):
        self._status_dir = status_dir
        self._account = settings['account']
        self._container = settings['container']
        ic_config = ConfigString(self.INTERNAL_CLIENT_CONFIG)
        self._swift_client = InternalClient(ic_config, 'Metadata sync', 3)
        self._status_file = os.path.join(self._status_dir, self._account,
                                         self._container)
        self._status_account_dir = os.path.join(self._status_dir, self._account)

    def handle(self, rows):
        raise NotImplementedError

    def get_last_row(self, db_id):
        raise NotImplementedError

    def save_last_row(self, row_id, db_id):
        raise NotImplementedError
