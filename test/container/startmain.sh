#!/bin/bash

# from https://github.com/FNNDSC/docker-swift-onlyone/blob/master/files/startmain.sh

#
# Make the rings if they don't exist already
#

# These can be set with docker run -e VARIABLE=X at runtime
SWIFT_PART_POWER=${SWIFT_PART_POWER:-7}
SWIFT_PART_HOURS=${SWIFT_PART_HOURS:-1}
SWIFT_REPLICAS=${SWIFT_REPLICAS:-1}

SWIFT_USERNAME=${SWIFT_USERNAME:-"userd:passd"}	# Default user & password
SWIFT_KEY=${SWIFT_KEY:-"keydd"}		# Default authkey

if [ -e /srv/account.builder ]; then
	echo "Ring files already exist in /srv, copying them to /etc/swift..."
	cp /srv/*.builder /etc/swift/
	cp /srv/*.gz /etc/swift/
else
	echo "No existing ring files, creating them..."

	(
	cd /etc/swift

	# 2^& = 128 we are assuming just one drive
	# 1 replica only

	swift-ring-builder object.builder create ${SWIFT_PART_POWER} ${SWIFT_REPLICAS} ${SWIFT_PART_HOURS}
	swift-ring-builder object.builder add r1z1-127.0.0.1:6010/sdb1 1
	swift-ring-builder object.builder rebalance
	swift-ring-builder container.builder create ${SWIFT_PART_POWER} ${SWIFT_REPLICAS} ${SWIFT_PART_HOURS}
	swift-ring-builder container.builder add r1z1-127.0.0.1:6011/sdb1 1
	swift-ring-builder container.builder rebalance
	swift-ring-builder account.builder create ${SWIFT_PART_POWER} ${SWIFT_REPLICAS} ${SWIFT_PART_HOURS}
	swift-ring-builder account.builder add r1z1-127.0.0.1:6012/sdb1 1
	swift-ring-builder account.builder rebalance
	)

 	# Back these up for later use
 	echo "Copying ring files to /srv to save them if it's a docker volume..."
 	cp /etc/swift/*.gz /srv
 	cp /etc/swift/*.builder /srv
fi

# Ensure device exists
mkdir -p /srv/devices/sdb1

# Ensure that supervisord's log directory exists
mkdir -p /var/log/supervisor

# Ensure that files in /srv are owned by swift.
if ! [[ "${SKIP_FILES_OWNED_FIX,,}" = *'y'* ]]; then
  chown -R swift:swift /srv
fi

# If you are going to put an ssl terminator in front of the proxy, then I believe
# the storage_url_scheme should be set to https. So if this var isn't empty, set
# the default storage url to https.
if [ ! -z "${SWIFT_STORAGE_URL_SCHEME}" ]; then
	echo "Setting default_storage_scheme to https in proxy-server.conf..."
	sed -i -e "s/storage_url_scheme = default/storage_url_scheme = https/g" /etc/swift/proxy-server.conf
	grep "storage_url_scheme" /etc/swift/proxy-server.conf
fi

# Set the credentials to be used into the environment
CREDENTIALS=`mktemp`
# If -e options given, use options variables first
# Else If .env file exists, use file variables
if [[ "${SWIFT_USERNAME}:${SWIFT_KEY}" != "userd:passd:keydd" ]]; then
	echo "Using environment credentials..."
elif [ -e /etc/swift/credentials.env ]; then
	echo "Using default credentials file: /etc/swift/credentials.env ..."
	cp /etc/swift/credentials.env $CREDENTIALS
else
	echo "Using default credentials..."
fi

# If secrets given, take precedence over variables
if [ -e /run/secret/swift-credentials ]; then
	echo "Using secrets credentials file: /run/secret/swift-credentials ..."
	cp /run/secret/swift-credentials $CREDENTIALS
fi

source $CREDENTIALS
export SWIFT_USERNAME SWIFT_KEY
rm $CREDENTIALS

# Set the credentials from the env into the swift config files
echo "Setting credentials in /etc/swift/proxy-server.conf..."
echo "
[filter:tempauth]
storage_url_scheme = default
use = egg:swift#tempauth
user_admin_admin = admin .admin .reseller_admin
user_$(echo $SWIFT_USERNAME | sed 's/:/_/g') = $SWIFT_KEY .admin" >> /etc/swift/proxy-server.conf

echo "Setting credentials in /etc/swift/dispersion.conf..."
cat > /etc/swift/dispersion.conf << EOF
[dispersion]
auth_url = http://127.0.0.1:8080/auth/v1.0
auth_user = $SWIFT_USERNAME
auth_key = $SWIFT_KEY
endpoint_type = internalURL
EOF

# Start supervisord
echo "Starting supervisord..."
/usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf

# Create default container
if [ ! -z "${SWIFT_DEFAULT_CONTAINER}" ]; then
	echo "Creating default container..."
	for container in ${SWIFT_DEFAULT_CONTAINER} ; do
	    echo "Creating container...${container}"
	    swift -A http://localhost:8080/auth/v1.0 -U chris:chris1234 -K testing post ${container}
	done
fi

# Create meta-url-key to allow temp download url generation
if [ ! -z "${SWIFT_TEMP_URL_KEY}" ]; then
  echo "Setting X-Account-Meta-Temp-URL-Key..."
  swift -A http://localhost:8080/auth/v1.0 -U chris:chris1234 -K testing post -m "Temp-URL-Key:${SWIFT_TEMP_URL_KEY}"
fi

/usr/bin/sudo -u elastic /bin/bash /elasticsearch-5.5.2/bin/elasticsearch \
    2>&1 > /var/log/elasticsearch.log &

# wait for elasticsearch to start
# https://stackoverflow.com/questions/21475639/wait-until-service-starts-in-bash-script
sleep 1
while ! grep -m1 'started' < /var/log/elasticsearch.log; do
    sleep 1
done
echo "Elasticsearch is active"

# create an index to use elasticsearch
curl -XPUT "http://localhost:9200/es-test"

export PYTHONPATH=/usr/local/lib/python3.6/dist-packages/:/swift_metadata_sync:/src/container-crawler
python3 -m swift_metadata_sync --log-level debug \
    --config /swift-metadata-sync/swift-metadata-sync.conf &

#
# Tail the log file for "docker log $CONTAINER_ID"
#

echo "Starting to tail /var/log/syslog...(hit ctrl-c if you are starting the container in a bash shell)"
exec tail -n 0 -F /var/log/syslog