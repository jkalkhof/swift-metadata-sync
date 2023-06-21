Swift Container Crawler
=======================

Library for iterating over OpenStack Swift container databases and acting on
each entry. The container database stores the names of the objects, the object
timestamp, and a flag indicating whether the record is a tombstone. Swift
replicates the state of the database across the container nodes.

This information is exactly what is required to detect and act on object changes
in the cluster, e.g. when an object is created, deleted, or its metadata is
modified.

The crawling class (ContainerCrawler) expects a set of configuration options
(`conf`) as a dictionary and a class to invoke for each database row. The
handler can opt into a single row processing mode or bulk processing by setting
the `bulk_process` option in `conf`.

For individually handled rows threading is implemented with green threads. The
number of threads can be controlled by setting the `workers` option, which
defaults to 10.

The required configuration settings are the Swift disk location (`devices`), the
crawler status directory (`status_dir`), and the number of items to process at a
time (`items_chunk`).

For an example of a program using the crawler, check out [Swift Metadata
Sync](https://github.com/swiftstack/swift-metadata-sync).
