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

application = service.Application("DoubanBot")

xmppclient = XMPPClient(jid.internJID(config.SCREEN_NAME), config.CONF.get('xmpp', 'pass'))
xmppclient.logTraffic = False
doubanBot=protocol.DoubanBotProtocol()
doubanBot.setHandlerParent(xmppclient)
VERSION = commands.getoutput("git describe").strip()
VersionHandler('DoubanBot', VERSION).setHandlerParent(xmppclient)
protocol.KeepAlive().setHandlerParent(xmppclient)
xmppclient.setServiceParent(application)

douban_checker = scheduling.DoubanChecker(doubanBot)
douban_authen = scheduling.AuthChecker(doubanBot)
# Run this once in a few seconds...
reactor.callLater(5, douban_checker)
reactor.callLater(20, douban_authen)

# And do it periodically
douban_checker_loop = task.LoopingCall(douban_checker)
douban_checker_loop.start(int(config.CONF.get('general', 'loop_sleep')), False)

douban_authen_loop = task.LoopingCall(douban_authen)
douban_authen_loop.start(900, False)
