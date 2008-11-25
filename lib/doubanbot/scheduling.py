import re
import datetime
from mx import DateTime

import models
import config
from doubanapi import DoubanClient
import douban

from twisted.internet import defer, threads

class AuthChecker(object):
    def __init__(self, client):
        self.client = client

    def __call__(self):
        session = models.Session()
        try:
            users = session.query(models.User).filter_by(auth=False).all()
            then = datetime.datetime.now() - datetime.timedelta(hours=24)
            for user in users:
                if user.last_check is None or user.last_check < then:
                    if user.status == 'online':
                        print "last_check: %s then: %s" %(str(user.last_check), str(then))
                        print "Sending authorization request to %s" %user.jid
                        self.__sendMessage(user.jid)
                        user.last_check = datetime.datetime.now()
                        session.add(user)
                        session.commit()
        finally:
            session.close()

    def __sendMessage(self, jid):
        msg = "Welcom to DoubanBot.\nPlease use the link below to authorize the bot for fetching you douban data:\n"
        hash = models.Authen.gen_authen_code(jid)
        auth_url = "%s/%s" %(config.AUTH_URL, hash)
        msg = "%s\n%s" %(msg, auth_url)
        return self.client.send_plain(jid, msg)

class DoubanChecker(object):
    def __init__(self, client):
        self.client = client

    def __call__(self):
        session = models.Session()
        try:
            ds = defer.DeferredSemaphore(tokens=config.BATCH_CONCURRENCY)
            for user in models.User.to_check(session, config.WATCH_FREQ):
                ds.run(self.__userCheck, user.jid, user.uid, user.key, user.secret)
        finally:
            session.close()

    def __userCheck(self, jid, uid, key, secret):
        def getFeed():
            return DoubanClient.getContactsBroadcasting(uid, key, secret)
        def callback(feed):
            if type(feed) is douban.BroadcastingFeed:
                self.onSuccess(jid, uid, key, secret, feed)
            elif feed is None:
                try:
                    session = models.Session()
                    user = models.User.by_jid(jid, session)
                    #user.uid = jid
                    user.name = jid
                    user.auth = False
                    session.add(user)
                    session.commit()
                    session.close()
                    print "Authorization status of jid: %s user: %s changed to False" %(jid, uid)
                except:
                    print "Error: change authorization status of jid: %s user: %s to False failed " %(jid, uid)
        d = threads.deferToThread(getFeed)
        d.addCallback(callback)
        return d

    def onSuccess(self, jid, uid, key, secret, feed):
        print "Success fetch broadcasting feed of user: %s" %uid
        feed.entry.reverse()
        try:
            session = models.Session()
            user = session.query(models.User).filter_by(jid=jid).one()
            msg = ''
            for entry in feed.entry:
                dt = datetime.datetime.fromtimestamp(DateTime.ISO.ParseDateTimeUTC(entry.published.text.decode('utf-8')))
                if not user.last_feed_dt or user.last_feed_dt < dt:
                    user.last_feed_dt = dt
                    # I hate python and twisted !
                    author = entry.author[0].name.text.decode('utf-8')
                    if author == user.name: continue
                    if not entry.title: continue
                    title = entry.title.text.decode('utf-8')
                    link = re.search('href=\"([^\"]+)\"', entry.content.text.decode('utf-8'))
                    if link and link.group(1): link = " %s" %link.group(1)
                    else: link = ''
                    if hasattr(entry, 'attribute'):
                        for att in entry.attribute:
                            if att.name == 'comment' and att.text: title = "%s  \"%s\"" %(title, att.text.decode('utf-8'))
                    msg = "%s\n%s:  %s%s" %(msg, author, title, link)
            msg = msg.lstrip("\n")
            if not user.is_quiet() and msg != '':
                self.client.send_plain(user.get_jid_full(), msg)
            user.last_check = datetime.datetime.now()
            session.add(user)
            session.commit()
        finally:
            session.close()
