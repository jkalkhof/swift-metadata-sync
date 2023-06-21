# https://github.com/FNNDSC/docker-swift-onlyone
# https://github.com/FNNDSC/docker-swift-onlyone/blob/master/Dockerfile
FROM fnndsc/docker-swift-onlyone:latest

RUN apt-get update &&\
    apt-get install --no-install-recommends -y wget openjdk-8-jre-headless git locales &&\
    apt-get clean &&\
    rm -rf /var/lib/apt/lists/*

RUN apt-get update && \
  apt-get install --no-install-recommends -y python3 python3-pip
RUN apt-get clean &&\
    rm -rf /var/lib/apt/lists/*

#RUN python3 -m pip install pip
RUN pip3 install setuptools

# pip3 install -U elasticsearch==5.5.2
RUN  pip3 install -U coverage nose flake8==3.5.0 mock && \
    pip3 install -U elasticsearch==5.4.0
#RUN pip3 uninstall -y hacking

RUN useradd -M -d /tmp elastic
RUN wget https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-5.5.2.tar.gz &&\
    tar -xvf elasticsearch-5.5.2.tar.gz && chown -R elastic elasticsearch-5.5.2

RUN  apt-get update && \
  apt-get install sudo
RUN apt-get clean &&\
    rm -rf /var/lib/apt/lists/*

# network tools
RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    net-tools curl \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    gcc g++ \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# sudo apt-get install build-essential python-dev python-pip liberasurecode-dev
RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3-dev build-essential python3-pip liberasurecode-dev \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# https://phoenixnap.com/kb/install-rust-ubuntu
RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y \
  rustc \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

RUN rustc -V

RUN pip3 install --upgrade pip
RUN pip3 install -U setuptools_rust
RUN pip3 install -U eventlet
RUN pip3 install -U cryptography
# swift needs pyeclib
# https://github.com/openstack/pyeclib
RUN pip3 install -U swift

# vim-nox
RUN apt-get update \
  && apt-get install -y vim-tiny \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

RUN echo "network.host: 0.0.0.0" >> /elasticsearch-5.5.2/config/elasticsearch.yml

# RUN pip install -e git://github.com/swiftstack/container-crawler.git@0.0.12#egg=container-crawler && \
# pip missing? use pip3 instead
# git clone -q git://github.com/osmboy/container-crawler /src/container-crawler
#RUN pip3 install -e git://github.com/osmboy/container-crawler#egg=container-crawler && \
COPY test/container/container-crawler /src/container-crawler
#RUN cd /src/container-crawler && python3 ./setup.py install

RUN mkdir /swift-metadata-sync && mkdir /var/lib/swift-metadata-sync

COPY test/container/launch.sh /swift-metadata-sync/
COPY ./swift_metadata_sync/*.py /swift_metadata_sync/
COPY test/container/swift-metadata-sync.conf /swift-metadata-sync/

RUN locale-gen en_US.UTF-8
ENV LANG='en_US.UTF-8' LANGUAGE='en_US:en' LC_ALL='en_US.UTF-8'

COPY test/container/startmain.sh /usr/local/bin/startmain.sh
RUN chmod 755 /usr/local/bin/*.sh

EXPOSE 8080
EXPOSE 9200

CMD /usr/local/bin/startmain.sh