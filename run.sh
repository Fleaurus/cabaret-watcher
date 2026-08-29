#!/bin/bash
cd "$(dirname "$0")"
/usr/bin/python3 watch.py >> watcher.log 2>&1
