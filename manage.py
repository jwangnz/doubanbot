#!/usr/bin/env python
from migrate.versioning.shell import main

main(url='sqlite:///doubanBot.sqlite3',repository='doubanbot2')
