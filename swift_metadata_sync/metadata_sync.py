from distutils.version import StrictVersion
import elasticsearch
import elasticsearch.helpers
import email.utils
import hashlib
import json
import logging
import os
import os.path

from swift.common.utils import decode_timestamps
from container_crawler.base_sync import BaseSync


class MetadataSync(BaseSync):
    DOC_TYPE = 'object'
    DOC_MAPPING = {
        "content-length": {"type": "long"},
        "content-type": {"type": "string"},
        "etag": {"type": "string", "index": "not_analyzed"},
        "last-modified": {"type": "date"},
        "x-object-manifest": {"type": "string"},
        "x-static-large-object": {"type": "boolean"},
        "x-swift-container": {"type": "string"},
        "x-swift-account": {"type": "string"},
        "x-swift-object": {"type": "string"},
        "x-timestamp": {"type": "date"},
        "x-trans-id": {"type": "string", "index": "not_analyzed"}
    }
    USER_META_PREFIX = 'x-object-meta-'

    def __init__(self, status_dir, settings, per_account=False):
        super().__init__(status_dir, settings)
        # Note that the syntax changed in Python 3.0: you can just say super().__init__() instead of super(ChildB, self).__init__()
        # super(MetadataSync, self).__init__(status_dir, settings, per_account)

        self.logger = logging.getLogger('swift-metadata-sync')
        es_hosts = settings['es_hosts']
        self._es_conn = elasticsearch.Elasticsearch(es_hosts)
        self._server_version = StrictVersion(
            self._es_conn.info()['version']['number'])
        self._index = settings['index']
        self._parse_json = settings.get('parse_json', False)
        self._pipeline = settings.get('pipeline')
        self._verify_mapping()

        self.logger.debug('metadata_sync: init: settings: %s' % repr(settings))
        self.logger.debug('metadata_sync: init: elasticsearch version: %s' % repr(self._server_version))

        self.debugLevel = 1

    def get_last_row(self, db_id):
        if not os.path.exists(self._status_file):
            return 0
        with open(self._status_file) as f:
            try:
                status = json.load(f)
                entry = status.get(db_id, None)
                if not entry:
                    return 0
                if entry['index'] == self._index:
                    return entry['last_row']
                else:
                    return 0
            except ValueError:
                return 0
        return 0

    def save_last_row(self, row_id, db_id):
        if not os.path.exists(self._status_account_dir):
            os.mkdir(self._status_account_dir)
        if not os.path.exists(self._status_file):
            with open(self._status_file, 'w') as f:
                json.dump({db_id: dict(last_row=row_id,
                                       index=self._index)}, f)
                return

        with open(self._status_file, 'r+') as f:
            try:
                status = json.load(f)
            except ValueError:
                status = {}
            status[db_id] = dict(last_row=row_id, index=self._index)
            f.seek(0)
            json.dump(status, f)
            f.truncate()
            return

    def handle(self, rows):
        self.logger.debug("Handling rows: %s" % repr(rows))
        self.handle_internal(rows, self._swift_client)

    # container_crawler/__init__.py : submit_items -> handle
    def handle_internal(self, rows, internal_client):
        self.logger.debug("Handling rows: %s" % repr(rows))
        if not rows:
            return []
        errors = []

        bulk_delete_ops = []
        mget_map = {}
        for row in rows:
            if row['deleted']:
                bulk_delete_ops.append({'_op_type': 'delete',
                                        '_id': self._get_document_id(row),
                                        '_index': self._index,
                                        '_type': self.DOC_TYPE})
                continue
            self.logger.debug('row: %s' % row)
            row_key = self._get_document_id(row)
            mget_map[row_key] = row

        if bulk_delete_ops:
            errors = self._bulk_delete(bulk_delete_ops)
        if not mget_map:
            self._check_errors(errors)
            return

        # self.logger.debug("multiple get map: %s" % repr(mget_map))

        stale_rows, mget_errors = self._get_stale_rows(mget_map)
        errors += mget_errors
        update_ops = [self._create_index_op(doc_id, row, internal_client)
                      for doc_id, row in stale_rows]
        _, update_failures = elasticsearch.helpers.bulk(
            self._es_conn,
            update_ops,
            raise_on_error=False,
            raise_on_exception=False
        )
        self.logger.debug("Index operations: %s" % repr(update_ops))

        for op in update_failures:
            op_info = op['index']
            if 'exception' in op_info:
                errors.append(op_info['exception'])
            else:
                errors.append("%s: %s" % (
                    op_info['_id'], self._extract_error(op_info)))
        self._check_errors(errors)

    def _check_errors(self, errors):
        if not errors:
            return

        for error in errors:
            self.logger.error(str(error))
        raise RuntimeError('Failed to process some entries')

    def _bulk_delete(self, ops):
        errors = []
        success_count, delete_failures = elasticsearch.helpers.bulk(
            self._es_conn, ops,
            raise_on_error=False,
            raise_on_exception=False
        )

        for op in delete_failures:
            op_info = op['delete']
            if op_info['status'] == 404:
                if op_info.get('result') == 'not_found':
                    continue
                # < 5.x Elasticsearch versions do not return "result"
                if op_info.get('found') is False:
                    continue
            if 'exception' in op_info:
                errors.append(op_info['exception'])
            else:
                errors.append("%s: %s" % (op_info['_id'],
                                          self._extract_error(op_info)))
        return errors

    # https://elasticsearch-py.readthedocs.io/en/v8.8.1/api.html#module-elasticsearch
    # https://elasticsearch-py.readthedocs.io/en/5.5.1/
    # https://elasticsearch-py.readthedocs.io/en/5.5.1/api.html#elasticsearch
    # https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-multi-get.html
    # https://stackoverflow.com/questions/49437215/serialization-error-using-elasticsearch-python
	# https://stackoverflow.com/questions/35441373/how-to-use-python-elasticsearch-mget-api
    def _get_stale_rows(self, mget_map):
        errors = []
        stale_rows = []

        # print('_get_stale_rows: mget_map.keys:',list(mget_map.keys()))
        results = self._es_conn.mget(body={'ids': list(mget_map.keys()) },
                                     index=self._index,
                                     refresh=True,
                                     _source=['x-timestamp'])
        docs = results['docs']
        for doc in docs:
            row = mget_map.get(doc['_id'])
            if not row:
                errors.append("Unknown row for ID %s" % doc['_id'])
                continue
            if 'error' in doc:
                errors.append("Failed to query %s: %s" % (
                              doc['_id'], str(doc['error'])))
                continue
            object_date = self._get_last_modified_date(row)
            # ElasticSearch only supports milliseconds
            object_ts = int(float(object_date) * 1000)
            if not doc['found'] or object_ts > doc['_source'].get(
                    'x-timestamp', 0):
                stale_rows.append((doc['_id'], row))
                continue

        # self.logger.debug("Stale rows: %s" % repr(stale_rows))
        self.logger.debug("Stale rows: %s" % repr(len(stale_rows)))

        return stale_rows, errors

    def _create_index_op(self, doc_id, row, internal_client):
        swift_hdrs = {'X-Newest': True}
        meta = internal_client.get_object_metadata(
            self._account, self._container, row['name'], headers=swift_hdrs)
        op = {'_op_type': 'index',
              '_index': self._index,
              '_type': self.DOC_TYPE,
              '_source': self._create_es_doc(meta, self._account,
                                             self._container,
                                             # row['name'].decode('utf-8'),
                                             row['name'],
                                             self._parse_json),
              '_id': doc_id}
        if self._pipeline:
            op['pipeline'] = self._pipeline
        return op

    """
        Verify document mapping for the elastic search index. Does not include
        any user-defined fields.
    """
    def _verify_mapping(self):
        index_client = elasticsearch.client.IndicesClient(self._es_conn)
        try:
            mapping = index_client.get_mapping(index=self._index,
                                               doc_type=self.DOC_TYPE)
        except elasticsearch.TransportError as e:
            if e.status_code != 404:
                raise
            if e.error != 'type_missing_exception':
                raise
            mapping = {}
        if not mapping.get(self._index, None) or \
                self.DOC_TYPE not in mapping[self._index]['mappings']:
            missing_fields = self.DOC_MAPPING.keys()
        else:
            current_mapping = mapping[self._index]['mappings'][
                self.DOC_TYPE]['properties']
            # We are not going to force re-indexing, so won't be checking the
            # mapping format
            missing_fields = [key for key in self.DOC_MAPPING.keys()
                              if key not in current_mapping]
        if missing_fields:
            new_mapping = dict([(k, v) for k, v in self.DOC_MAPPING.items()
                                if k in missing_fields])
            # Elasticsearch 5.x deprecated the "string" type. We convert the
            # string fields into the appropriate 5.x types.
            # TODO: Once we remove  support for the 2.x clusters, we should
            # remove this code and create the new mappings for each field.
            if self._server_version >= StrictVersion('5.0'):
                new_mapping = dict([(k, self._update_string_mapping(v))
                                    for k, v in new_mapping.items()])
            index_client.put_mapping(index=self._index, doc_type=self.DOC_TYPE,
                                     body={'properties': new_mapping})

    @staticmethod
    def _create_es_doc(meta, account, container, key, parse_json=False):
        def _parse_document(value):
            try:
                return json.loads(value.decode('utf-8'))
            except ValueError:
                return value.decode('utf-8')

        es_doc = {}
        # ElasticSearch only supports millisecond resolution
        es_doc['x-timestamp'] = int(float(meta['x-timestamp']) * 1000)
        # Convert Last-Modified header into a millis since epoch date
        ts = email.utils.mktime_tz(
            email.utils.parsedate_tz(meta['last-modified'])) * 1000
        es_doc['last-modified'] = ts
        es_doc['x-swift-object'] = key
        es_doc['x-swift-account'] = account
        es_doc['x-swift-container'] = container

        # user_meta_keys = dict(
        #     [(k.split(MetadataSync.USER_META_PREFIX, 1)[1].decode('utf-8'),
        #       _parse_document(v) if parse_json else v.decode('utf-8'))
        #      for k, v in meta.items()
        #      if k.startswith(MetadataSync.USER_META_PREFIX)])

        user_meta_keys = dict(
            [(k.split(MetadataSync.USER_META_PREFIX, 1)[1],
              _parse_document(v) if parse_json else v)
             for k, v in meta.items()
             if k.startswith(MetadataSync.USER_META_PREFIX)])

        es_doc.update(user_meta_keys)
        for field in MetadataSync.DOC_MAPPING.keys():
            if field in es_doc:
                continue
            if field not in meta:
                continue
            es_doc[field] = meta[field]
        return es_doc

    @staticmethod
    def _get_last_modified_date(row):
        ts, content, meta = decode_timestamps(row['created_at'])
        # NOTE: the meta timestamp will always be latest, as it will be updated
        # when content type is updated
        return meta

    @staticmethod
    def _extract_error(err_info):
        if 'error' not in err_info or 'root_cause' not in err_info['error']:
            return str(err_info['status'])

        err = err_info['error']['root_cause']
        try:
            return '%s: %s' % (err, err_info['error']['caused_by']['reason'])
        except KeyError:
            return err

    @staticmethod
    def _update_string_mapping(mapping):
        if mapping['type'] != 'string':
            return mapping
        if 'index' in mapping and mapping['index'] == 'not_analyzed':
            return {'type': 'keyword'}
        # This creates a mapping that is both searchable as a text and keyword
        # (the default  behavior in Elasticsearch for 2.x string types).
        return {
            'type': 'text',
            'fields': {
                'keyword': {
                    'type': 'keyword'}
            }
        }

    def _get_document_id(self, row):
        unique_str = '/'.join([self._account,
                      self._container,
                      row['name']])
        unique_str = unique_str.encode('utf-8')
        if (self.debugLevel > 1): self.logger.debug('_get_document_id: unique_str: %s' % unique_str)
        unique_id = hashlib.sha256(unique_str).hexdigest()
        if (self.debugLevel > 1): self.logger.debug('_get_document_id: unique_id: %s' % repr(unique_id))
        return unique_id
