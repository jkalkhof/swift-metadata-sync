#!/bin/bash

set -e

# Make sure all of the .pid files are removed -- services will not start
# otherwise
# find /var/lib/ -name *.pid -delete
# find /var/run/ -name *.pid -delete

# Copied from the docker swift container. Unfortunately, there is no way to
# plugin an additional invocation to start swift-s3-sync, so we had to do this.

# /usr/sbin/service rsyslog start
# /usr/sbin/service rsync start
# /usr/sbin/service memcached start

# set up storage
# mkdir -p /swift/nodes/1 /swift/nodes/2 /swift/nodes/3 /swift/nodes/4

# use mounted storage instead
# -v swift_storage:/srv
# rm -r -f /swift/nodes/1/node/sdb1
# ln -s /srv/devices/sdb1 /swift/nodes/1/node/
# mkdir -p /var/run/swift
# /usr/bin/sudo /bin/chown -R swift:swift /var/run/swift

# for i in `seq 1 4`; do
#     if [ ! -e "/srv/$i" ]; then
#         ln -s /swift/nodes/$i /srv/$i
#     fi
# done
#
# mkdir -p /srv/1/node/sdb1 /srv/2/node/sdb2 /srv/3/node/sdb3 /srv/4/node/sdb4 \
#   /var/run/swift
#
# /usr/bin/sudo /bin/chown -R swift:swift /swift/nodes /etc/swift /srv/1 /srv/2 \
#     /srv/3 /srv/4 /var/run/swift

#/usr/bin/sudo -u swift /swift/bin/remakerings
# /usr/bin/sudo -u swift bash /swift/bin/remakerings

# use commands from launch.sh instead of "startmain" which doesn't exist!
#/usr/bin/sudo -u swift /swift/bin/startmain
#/usr/bin/sudo -u swift bash /swift/bin/startmain
# from /swift/bin/launch.sh
# /usr/bin/sudo -u swift bash -c "/usr/local/bin/swift-init main start"
# /usr/bin/sudo -u swift bash -c "/usr/local/bin/swift-init rest start"
#/usr/bin/sudo -u swift /usr/local/bin/supervisord -n -c /etc/supervisord.conf

# PYTHONPATH=/opt/ss/lib/python2.7/dist-packages:/swift-metadata-sync \
#     python -m swift_metadata_sync --log-level debug \
#     --config /swift-metadata-sync/test/container/swift-metadata-sync.conf &

/usr/bin/sudo -u elastic /bin/bash /elasticsearch-5.5.2/bin/elasticsearch \
    2>&1 > /var/log/elasticsearch.log &

# wait for elasticsearch to start
sleep 2

export PYTHONPATH=/usr/local/lib/python3.8/dist-packages/:/swift_metadata_sync
python3 -m swift_metadata_sync --log-level debug \
    --config /swift-metadata-sync/swift-metadata-sync.conf &

# /usr/local/bin/supervisord -n -c /etc/supervisord.conf
