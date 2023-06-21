import eventlet
eventlet.patcher.monkey_patch(all=True)

import os.path
import time
import traceback

from swift.common.db import DatabaseConnectionError
from swift.common.ring import Ring
from swift.common.ring.utils import is_local_device
from swift.common.utils import whataremyips, hash_path, storage_directory
from swift.container.backend import DATADIR, ContainerBroker


class ContainerCrawler(object):
    def __init__(self, conf, handler_class, logger=None):
        self.logger = logger
        self.conf = conf
        self.root = conf['devices']
        self.bulk = conf.get('bulk_process', False)
        self.interval = 10
        self.swift_dir = '/etc/swift'
        self.container_ring = Ring(self.swift_dir, ring_name='container')

        self.status_dir = conf['status_dir']
        self.myips = whataremyips('0.0.0.0')
        self.items_chunk = conf['items_chunk']
        self.poll_interval = conf.get('poll_interval', 5)
        self.handler_class = handler_class

        if not self.bulk:
            self._init_workers(conf)

        self.log('debug', 'Created the Container Crawler instance')

    def _init_workers(self, conf):
        self.workers = conf.get('workers', 10)
        self.pool = eventlet.GreenPool(self.workers)
        self.work_queue = eventlet.queue.Queue(self.workers * 2)

        # max_size=None means a Queue is infinite
        self.error_queue = eventlet.queue.Queue(maxsize=None)
        self.stats_queue = eventlet.queue.Queue(maxsize=None)
        for _ in range(0, self.workers):
            self.pool.spawn_n(self._worker)

    def _worker(self):
        while 1:
            work = self.work_queue.get()
            if not work:
                self.work_queue.task_done()
                break
            row, handler = work
            try:
                handler.handle(row)
            except Exception as e:
                self.error_queue.put((row, e))
            self.work_queue.task_done()

    def _stop(self):
        for _ in range(0, self.workers):
            self.work_queue.put(None)
        self.pool.waitall()

    def _check_errors(self):
        if self.error_queue.empty():
            return

        while not self.error_queue.empty():
            row, error = self.error_queue.get()
            self.log('error', 'Failed to handle row %s: %r' % (
                row['ROWID'], error))
        raise RuntimeError('Failed to process rows')

    def log(self, level, message):
        if not self.logger:
            return
        getattr(self.logger, level)(message)

    def get_broker(self, account, container, part, node):
        db_hash = hash_path(account, container)
        db_dir = storage_directory(DATADIR, part, db_hash)
        db_path = os.path.join(self.root, node['device'], db_dir,
                               db_hash + '.db')
        return ContainerBroker(db_path, account=account, container=container)

    def dump(self, obj):
        for attr in dir(obj):
            print("obj.%s = %r" % (attr, getattr(obj, attr)))

    # see also https://github.com/openstack/swift/blob/master/test/unit/common/test_internal_client.py
    # see also https://github.com/openstack/swift/blob/master/swift/common/internal_client.py
    # run_once -> handle_container -> process_items -> submit_items -> metadata_sync.py : handle
    def submit_items(self, handler, rows):
        if self.bulk:
            # print('handler: ',dir(handler))
            # print('handler: ', vars(handler))
            # self.dump(handler)
            handler.handle(rows)
            return

        for row in rows:
            self.work_queue.put((row, handler))
        self.work_queue.join()
        self._check_errors()

    # run_once -> handle_container -> process_items
    def process_items(self, handler, rows, nodes_count, node_id):
        owned_rows = filter(
            lambda row: row['ROWID'] % nodes_count == node_id, rows)
        self.submit_items(handler, owned_rows)

        verified_rows = filter(
            lambda row: row['ROWID'] % nodes_count != node_id, rows)
        self.submit_items(handler, verified_rows)

    # run_once -> handle_container
    def handle_container(self, settings):
        part, container_nodes = self.container_ring.get_nodes(
            settings['account'], settings['container'])
        nodes_count = len(container_nodes)
        handler = self.handler_class(self.status_dir, settings)

        for index, node in enumerate(container_nodes):
            if not is_local_device(self.myips, None, node['ip'],
                                   node['port']):
                continue
            broker = self.get_broker(settings['account'],
                                     settings['container'],
                                     part, node)
            broker_info = broker.get_info()
            last_row = handler.get_last_row(broker_info['id'])
            if not last_row:
                last_row = 0
            try:
                items = broker.get_items_since(last_row, self.items_chunk)
            except DatabaseConnectionError:
                continue
            if items:
                self.process_items(handler, items, nodes_count, index)
                handler.save_last_row(items[-1]['ROWID'], broker_info['id'])
            return

    def run_always(self):
        # Since we don't support reloading, the daemon should quit if there are
        # no containers configured
        if 'containers' not in self.conf or not self.conf['containers']:
            return
        self.log('debug', 'Entering the poll loop')
        while True:
            start = time.time()
            self.run_once()
            elapsed = time.time() - start
            if elapsed < self.poll_interval:
                time.sleep(self.poll_interval - elapsed)

    def run_once(self):
        for container_settings in self.conf['containers']:
            try:
                self.handle_container(container_settings)
            except Exception as e:
                account = container_settings.get('account', 'N/A')
                container = container_settings.get('container', 'N/A')
                self.log('error', "Failed to process %s/%s with %s: %s" % (
                    account, container, self.handler_class, repr(e)))
                self.log('error', traceback.format_exc(e))
