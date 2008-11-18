#!/usr/bin/env python
"""
Configuration for DoubanBot

"""

import ConfigParser
import commands

CONF = ConfigParser.ConfigParser()
CONF.read('dbb.conf')
SCREEN_NAME = CONF.get('xmpp', 'jid')
#VERSION = commands.getoutput("git describe").strip()

API_KEY = CONF.get('general', 'api_key')
API_SECRET = CONF.get('general', 'api_secret')
API_SERVER = CONF.get('general', 'api_server')

AUTH_URL = CONF.get('general', 'auth_url')

BATCH_CONCURRENCY = CONF.getint('general', 'batch_concurrency')
WATCH_FREQ = CONF.getint('general', 'watch_freq')

ADMINS = CONF.get("general", "admins").split(' ')
