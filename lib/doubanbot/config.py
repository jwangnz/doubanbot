#!/usr/bin/env python
"""
Configuration for DoubanBot

"""

import ConfigParser
import commands

CONF = ConfigParser.ConfigParser()
CONF.read('dbb.conf')

SCREEN_NAME = CONF.get('xmpp', 'jid')
PRIORITY = CONF.getint('xmpp', 'priority')
NAME = CONF.get('general', 'name')

BATCH_CONCURRENCY = CONF.getint('general', 'batch_concurrency')
WATCH_FREQ = CONF.getint('general', 'watch_freq')
ADMINS = CONF.get("general", "admins").split(' ')

AUTH_URL = CONF.get('auth', 'url')
AUTH_CALLBACK = CONF.get('auth', 'callback')
AUTH_TIMEOUT = CONF.get('auth', 'timeout')

DATABASE = CONF.get('database', 'db')

API_KEY = CONF.get('api', 'key')
API_SECRET = CONF.get('api', 'secret')
API_SERVER = CONF.get('api', 'server')

