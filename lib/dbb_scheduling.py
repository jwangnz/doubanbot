import re
import datetime
from mx import DateTime

import models
import dbb_config
from dbb_douban import DoubanClient

from twisted.internet import defer

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
        return DoubanClient.getContactsBroadcasting(uid, key, secret).addCallbacks(
            callback=lambda feed: self.onSucess(jid, uid, key, secret, feed),
            errback=lambda err: self.onError(jid, uid, key, secret, err))

    def onSucess(self, jid, uid, key, secret, feed):
        print "Success fetch broadcasting feed of user: %s" %uid
        feed.entry.reverse()
        try:
            session = models.Session()
            user = session.query(models.User).filter_by(jid=jid).one()
            for entry in feed.entry:
                dt = datetime.datetime.fromtimestamp(DateTime.ISO.ParseDateTimeUTC(entry.published.text.decode('utf-8')))
                if not user.last_feed_dt or user.last_feed_dt < dt:
                    user.last_feed_dt = dt
                    # I hate python and twisted !
                    author = entry.author[0].name.text.decode('utf-8')
                    if author == user.name: continue
                    title = entry.title.text.decode('utf-8')
                    link = re.search('href=\"([^\"]+)\"', entry.content.text.decode('utf-8'))
                    if link and link.group(1): link = " %s" %link.group(1)
                    else: link = ''
                    if not user.is_quiet():
                        self.client.send_plain(user.get_jid_full(), "%s: %s%s" %(author, title, link))
            session.add(user) 
            session.commit()
        finally:        
            session.close()

    def onError(self, jid, uid, key, secret, err):
        print "the error callback was called when process jid: %s user: %s, error: %s" %(jid, uid, str(err))
