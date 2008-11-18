import sys
sys.path.append("lib")

from twisted.application import service
from twisted.internet import task, reactor
from twisted.words.protocols.jabber import jid
from wokkel.client import XMPPClient
#from wokkel.generic import VersionHandler

import dbb_config
import dbb_protocol
import dbb_scheduling

application = service.Application("DoubanBot")

xmppclient = XMPPClient(jid.internJID(dbb_config.SCREEN_NAME), dbb_config.CONF.get('xmpp', 'pass'))
xmppclient.logTraffic = False
doubanBot=dbb_protocol.DoubanBotProtocol()
doubanBot.setHandlerParent(xmppclient)
#VersionHandler('DoubanBot', dbb_config.VERSION).setHandlerParent(xmppclient)
dbb_protocol.KeepAlive().setHandlerParent(xmppclient)
xmppclient.setServiceParent(application)

douban_checker = dbb_scheduling.DoubanChecker(doubanBot)
# Run this once in a few seconds...
reactor.callLater(5, douban_checker)

# And do it periodically
douban_checker_loop = task.LoopingCall(douban_checker)
douban_checker_loop.start(int(dbb_config.CONF.get('general', 'loop_sleep')), False)
