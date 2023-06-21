#!/usr/bin/python

from setuptools import setup

with open('requirements.txt') as reqs_file:
    reqs = [req.strip() for req in reqs_file]

setup(name='container-crawler',
      version='0.0.1',
      author='SwiftStack',
      author_email='info@swiftstack.com',
      test_suite='nose.collector',
      url='https://github.com/swiftstack/container-crawler',
      packages=['container_crawler'],
      install_requires = reqs
     )
