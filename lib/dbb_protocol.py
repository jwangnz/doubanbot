from twisted.internet import task
from twisted.words.xish import domish
from twisted.words.protocols.jabber.jid import JID
from wokkel.xmppim import MessageProtocol, PresenceClientProtocol
from wokkel.xmppim import AvailablePresence
from wokkel.client import XMPPHandler

import dbb_commands
import dbb_config
import models

class DoubanBotProtocol(MessageProtocol, PresenceClientProtocol):

    def __init__(self):
        super(DoubanBotProtocol, self).__init__()
        ##self._watching=-1
        self._users=-1

    def connectionInitialized(self):
        MessageProtocol.connectionInitialized(self)
        PresenceClientProtocol.connectionInitialized(self)

    def connectionMade(self):
        print "Connected!"

        self.commands=dbb_commands.all_commands
        print "Loaded commands: ", `self.commands.keys()`

        # send initial presence
        ##self._watching=-1
        self._users=-1
        self.update_presence()

    def update_presence(self):
        session=models.Session()
        try:
           users=session.query(models.User).count()
           if users != self._users:
                status = "Working for %s users, type help for usage info" %users
                self.available(None, None, {None: status})
                self._users = users
        finally:
            session.close()

    def connectionLost(self, reason):
        print "Disconnected!"

    def typing_notification(self, jid):
        """Send a typing notification to the given jid."""

        msg = domish.Element((None, "message"))
        msg["to"] = jid
        msg["from"] = dbb_config.SCREEN_NAME
        msg.addElement(('jabber:x:event', 'x')).addElement("composing")

        self.send(msg)

    def send_plain(self, jid, content):
        msg = domish.Element((None, "message"))
        msg["to"] = jid
        msg["from"] = dbb_config.SCREEN_NAME
        msg["type"] = 'chat'
        msg.addElement("body", content=content)

        self.send(msg)
         

    def get_user(self, msg, session):
        jid = JID(msg['from'])
        try:
            user = models.User.by_jid(jid.userhost(), session)
        except:
            print "Getting user without the jid in the DB (%s)" % jid.full()
            user = models.User.update_status(jid.userhost(), None, session)
            self.subscribe(jid)
        return user;

    def onMessage(self, msg):
        if hasattr(msg, "type") and msg["type"] == 'chat' and hasattr(msg, "body") and msg.body:
            self.typing_notification(msg['from'])
            session = models.Session()
            user = self.get_user(msg, session)
            if user.auth is False:
                hash = models.Authen.gen_authen_code(user.jid)
                link = "%s/%s" %(dbb_config.AUTH_URL, hash)
                message = "Please use the link below to authorise the bot for fetching your douban data:\n%s" %link
                self.send_plain(msg['from'], message)
            else: 
                a=unicode(msg.body).split(' ', 1)
                args = None
                if len(a) > 1:
                    args=a[1]
                if self.commands.has_key(a[0].lower()):
                    try:
                        user.jid_full = msg['from']
                        self.commands[a[0].lower()](self.get_user(msg, session),
                            self, args, session)
                        session.commit()
                    finally:
                        session.close()
                else:
                    self.send_plain(msg['from'], 'No such command: ' + a[0])
            self.update_presence()

    # presence stuff
    def availableReceived(self, entity, show=None, statuses=None, priority=0):
        if entity.userhost() == JID(dbb_config.SCREEN_NAME).userhost():
            return
        print "Available from %s (%s, %s)" % (entity.full(), show, statuses)
        models.User.update_status(entity.userhost(), show)

    def unavailableReceived(self, entity, statuses=None):
        print "Unavailable from %s" % entity.userhost()
        models.User.update_status(entity.userhost(), 'unavailable')

    def subscribedReceived(self, entity):
        print "Subscribe received from %s" % (entity.userhost())
        welcome_message = """Welcome to DoubanBot

The bot watch you douban contacts' broadcasting for you!

"""
        session = models.Session()
        hash = models.Authen.gen_authen_code(entity.userhost(), session)
        auth_url = "%s/%s" %(dbb_config.AUTH_URL, hash)
        self.send_plain(entity.full(), "%s\n use the link below to authorise the bot for fetching you douban data:\n\n%s\n" %(welcome_message, auth_url))
        try:
            msg = "New subscriber: %s ( %d )" % (entity.userhost(),
                session.query(models.User).count())
            for a in dbb_config.ADMINS:
                self.send_plain(a, msg)
        finally:
            session.close()

    def unsubscribedReceived(self, entity):
        print "Unsubscribed received from %s" % (entity.userhost())
        models.User.update_status(entity.userhost(), 'unsubscribed')
        self.unsubscribe(entity)
        self.unsubscribed(entity)

    def subscribeReceived(self, entity):
        print "Subscribe received from %s" % (entity.userhost())
        self.subscribe(entity)
        self.subscribed(entity)
        self.update_presence()

    def unsubscribeReceived(self, entity):
        print "Unsubscribe received from %s" % (entity.userhost())
        models.User.update_status(entity.userhost(), 'unsubscribed')
        self.unsubscribe(entity)
        self.unsubscribed(entity)
        self.update_presence()

# From https://mailman.ik.nu/pipermail/twisted-jabber/2008-October/000171.html
class KeepAlive(XMPPHandler):

    interval = 300
    lc = None

    def connectionInitialized(self):
        self.lc = task.LoopingCall(self.ping)
        self.lc.start(self.interval)

    def connectionLost(self, *args):
        if self.lc:
            self.lc.stop()

    def ping(self):
        print "Stayin' alive"
        self.send(" ")
