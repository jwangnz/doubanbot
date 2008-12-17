import sys
sys.path.append("lib")

import commands
from twisted.application import service
from twisted.internet import task, reactor
from twisted.words.protocols.jabber import jid
from wokkel.client import XMPPClient
from wokkel.generic import VersionHandler

from doubanbot import config
from doubanbot import protocol
from doubanbot import scheduling
from doubanbot import doubanapi

doubanapi.API_KEY = config.API_KEY
doubanapi.API_SECRET = config.API_SECRET

application = service.Application(config.NAME)

xmppclient = XMPPClient(jid.internJID(config.SCREEN_NAME), config.CONF.get('xmpp', 'pass'))
xmppclient.logTraffic = False
doubanBot=protocol.DoubanBotProtocol()
doubanBot.setHandlerParent(xmppclient)
VERSION = commands.getoutput("git describe").strip()
VersionHandler(config.NAME, VERSION).setHandlerParent(xmppclient)
protocol.KeepAlive().setHandlerParent(xmppclient)
xmppclient.setServiceParent(application)

