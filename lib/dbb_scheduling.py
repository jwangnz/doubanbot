import re
import datetime
from mx import DateTime

import models
import dbb_config
from dbb_douban import DoubanClient

from twisted.internet import defer, threads

class DoubanChecker(object):
    def __init__(self, client):
        self.client = client

    def __call__(self):
        session = models.Session()
        try:
            ds = defer.DeferredSemaphore(tokens=dbb_config.BATCH_CONCURRENCY)
            for user in models.User.to_check(session, dbb_config.WATCH_FREQ):
                ds.run(self.__userCheck, user.jid, user.uid, user.key, user.secret)
        finally:
            session.close()

    def __userCheck(self, jid, uid, key, secret):
        def getFeed():
            return DoubanClient.getContactsBroadcasting(uid, key, secret)
        def callback(feed):
            if feed is False:
                print "Error: fetching user: %s contacts broadcasting feed failed" %uid
            else:
                self.onSuccess(jid, uid, key, secret, feed)
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

