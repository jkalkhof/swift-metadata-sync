#!/bin/bash

set -e

/usr/bin/sudo -u elastic /bin/bash /elasticsearch-5.5.2/bin/elasticsearch \
    2>&1 > /var/log/elasticsearch.log &

# wait for elasticsearch to start
sleep 2

export PYTHONPATH=/usr/local/lib/python3.8/dist-packages/:/swift_metadata_sync
python3 -m swift_metadata_sync --log-level debug \
    --config /swift-metadata-sync/swift-metadata-sync.conf &


