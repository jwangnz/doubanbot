import re
import time
import datetime
import douban

import models
import config
import doubanapi
import protocol

from twisted.python import log
from twisted.internet import defer, reactor, threads, task
from twisted.words.protocols.jabber.jid import JID


private_sem = defer.DeferredSemaphore(tokens=20)
available_sem = defer.DeferredSemaphore(tokens=5)

class JidSet(set):
 
    def bare_jids(self):
        return set([JID(j).userhost() for j in self])


class UserStuff(JidSet):

    loop_time = 30

    def __init__(self, short_jid, last_cb_id, last_dm_id):
        super(UserStuff, self).__init__()
        self.short_jid = short_jid
        self.last_cb_id = last_cb_id
        self.last_dm_id = last_dm_id

        self.uid = None
        self.name = None
        self.key = None
        self.secret = None
        self.auth = None
        self.active = None
        self.quiet_until = None

        self.loop = None

    def __deliver_message(self, entry):
        # 
        conn = protocol.current_conn 
        for jid in self.bare_jids():
            conn.send_html(jid, entry)

    @models.wants_session
    def _deferred_write(self, jid, mprop, new_val, session):
        u = models.User.by_jid(jid, session)
        setattr(u, mprop, new_val)
        try:
            session.commit()
        except:
            log.err()

    def _maybe_update_prop(self, prop, mprop):
        old_val = getattr(self, prop)
        def f(x):
            new_val = getattr(self, prop)
            if old_val != new_val:
                threads.deferToThread(
                    self._deferred_write, self.short_jid, mprop, new_val)
        return f


    def __call__(self):
        if self.uid and self.key and self.secret and protocol.current_conn:
            global private_sem
            private_sem.run(self.__get_user_stuff)

    def _gotDMResult(self, feed):
        plains = []
        feed.entry.reverse()
        hasNew = False
        for a in feed.entry: 
            entry = doubanapi.Entry(a)
            entry_id = int(entry.id)
            if entry_id > self.last_dm_id:
                self.last_dm_id = entry_id
                hasNew = True
                if entry.isRead is True:
                    continue

                plain = "Got a doumail from %s: %s\n%s" % (
                    entry.authorName.decode('utf-8'), 
                    entry.title.decode('utf-8'), entry.alternateLink)
                plains.append(plain)

        if len(plains) > 0: 
            log.msg("User: %s got %s new doumail" % (self.uid, len(plains)))
            conn = protocol.current_conn
            for jid in self.bare_jids():
                conn.send_plain(jid, "\n".join(plains))

        if hasNew:
           threads.deferToThread(self._deferred_write, self.short_jid, 'last_dm_id', self.last_dm_id) 

            
    def _gotCBResult(self, feed):
        plains = []
        htmls = []
        feed.entry.reverse()
        for a in feed.entry:
            entry = doubanapi.Entry(a)
            entry_id = int(entry.id) 
            if entry_id > self.last_cb_id:
                self.last_cb_id = entry_id
                if self.name == entry.authorName.decode('utf-8'):
                    continue
                plain = "%s: %s " % (entry.authorName.decode('utf-8'), entry.title.decode('utf-8'))
                html = "<a href=\"%s\">%s</a>: %s" % (entry.authorLink, entry.authorName.decode('utf-8'), entry.htmlContent.decode('utf-8'))
                comment = entry.comment
                if comment: 
                    plain += " \"%s\"" % comment.decode('utf-8')
                    html += " \"%s\"" % comment.decode('utf-8')
                rating = entry.rating
                if rating:
                    star = " %s%s" %('\xe2\x98\x85'.decode('utf-8') * int(rating), '\xe2\x98\x86'.decode('utf-8') * (5 - int(rating)))
                    plain += star
                    html += star
                link = entry.contentLink
                if link:
                    plain += " %s" % link
                html = html.replace("&lt;", "<").replace("&gt;", ">").replace('&amp;', '&')
                plains.append(plain)
                htmls.append(html)

        if len(plains) > 0:
            conn = protocol.current_conn
            for jid in self.bare_jids():
                #conn.send_html(jid, "\n".join(plains), "<br />".join(htmls))
                conn.send_plain(jid, "\n".join(plains))
            threads.deferToThread(self._deferred_write, self.short_jid, 'last_cb_id', self.last_cb_id)

    def __get_user_stuff(self):
        log.msg("Getting contacts broadcasting of: %s for %s" % (self.uid, self.short_jid))
        api = doubanapi.Douban(self.uid, self.key, self.secret)         
        api.getContactsBroadcasting().addCallbacks(
            callback=lambda feed: self._gotCBResult(feed),
            errback=lambda err: self._reportError(err))
        api.getDoumailFeed('/doumail/inbox').addCallbacks(
            callback=lambda feed: self._gotDMResult(feed),
            errback=lambda err: self._reportError(err))         

    def _reportError(self, e):
        log.msg("Error getting user data for %s: %s" % (self.short_jid, e.getErrorMessage()))

    def start(self):
        if not self.loop:
            log.msg("Starting %s" % self.short_jid)
            self.loop = task.LoopingCall(self)
            self.loop.start(self.loop_time)

    def stop(self):
        if self.loop:
            log.msg("Stopping user %s" % self.short_jid)
            self.loop.stop()
            self.loop = None

class RoutinChecker(object):
    "maintain user auth status"

    loop_time = 60

    def __init__(self):
        self.loop = None 
        self.users = {}

    def add(self, short_jid):
        log.msg("Adding %s to RoutineChecker" % short_jid)
        if not self.users.has_key(short_jid):
            self.users[short_jid] = 1

    def remove(self, short_jid):
        log.msg("Removing %s from RoutineChecker" % short_jid)
        if self.users.has_key(short_jid):
            del self.users[short_jid]

    def start(self):
        if not self.loop:
            log.msg("Starting RoutineCheck")
            self.loop = task.LoopingCall(self)
            self.loop.start(self.loop_time)

    def stop(self):
        if self.loop:
            log.msg("Stopping UserCheck")
            self.loop.stop()
            self.loop = None

    def reset(self):
        self.users = {}
        self.stop()
        self.start()

    @models.wants_session
    def __check_user_(self, jid, session):
        def check(u):
            if (u[1][0] and u[1][1] and u[1][2] and u[1][3]):
                self.remove(jid)
                enable_user(jid)
        return threads.deferToThread(_load_user, jid).addCallback(check)

    def __call__(self):
        global available_sem
        if len(self.users) and protocol.current_conn:
            for jid in self.users.keys():
                available_sem.run(self.__check_user_, jid)
         

class UserRegistry(object):

    def __init__(self):
        self.users = {}
    
    def add(self, short_jid, full_jid, last_cb_id, last_dm_id):
        log.msg("Adding %s as %s" % (short_jid, full_jid))
        if not self.users.has_key(short_jid):
            self.users[short_jid] = UserStuff(short_jid, last_cb_id, last_dm_id)
        self.users[short_jid].add(full_jid)

    def set_creds(self, short_jid, uid, name, key, secret, quiet_until):
        u = self.users.get(short_jid)
        if not u:
            log.msg("Couldn't find %s to set creds" % short_jid)
            return

        u.uid = uid
        u.name = name
        u.key = key
        u.secret = secret
        u.quiet_until = u.quiet_until
        available = u.uid and u.key and u.secret

        global checker
        if not available:
            checker.add(short_jid)
        else:
            checker.remove(short_jid)

        if u.quiet_until is None:
            quiet_seconds = 0
        else:
            quiet_seconds = time.time() - time.mktime((datetime.datetime.now() - u.quiet_until).timetuple())

        if available and quiet_seconds > 0:
            u.stop()
            reactor.callLater(quiet_seconds, u.start) 
        elif available and not u.loop:
            u.start()
        elif u.loop and not available:
            u.stop()

    def remove(self, short_jid, full_jid=None):
        q = self.users.get(short_jid)
        if not q:
            return
        q.discard(full_jid)
        if not q:
            q.stop()
            del self.users[short_jid]

users = UserRegistry()
checker = RoutinChecker()

def _entity_to_jid(entity):
    return entity if isinstance(entity, basestring) else entity.userhost()

@models.wants_session
def _load_user(entity, session):
    jid = _entity_to_jid(entity)
    try:
        u = models.User.by_jid(jid, session)
    except:
        log.msg("Getting user without the jid in the DB (%s)" % jid)
        u = models.User.update_status(jid, None, session)
    if u.active is False or u.auth is False:
        return ((u.last_cb_id, u.last_dm_id), ('', '', '', '', u.quiet_until))
    return ((u.last_cb_id, u.last_dm_id), (u.uid, u.name, u.key, u.secret, u.quiet_until))

def _init_user(u, short_jid, full_jids):
    if u:
        for j in full_jids:
            users.add(short_jid, j, u[0][0], u[0][1])
        users.set_creds(short_jid, u[1][0], u[1][1], u[1][2], u[1][3], u[1][4])

def enable_user(jid):
    def process():
        return threads.deferToThread(_load_user, jid).addCallback(
            _init_user, jid, users.users.get(jid, []))
    global available_sem
    available_sem.run(process)

def disable_user(jid):
    users.set_creds(jid, None, None, None, None, None)

def available_user(entity):
    def process():
        return threads.deferToThread(_load_user, entity).addCallback(
            _init_user, entity.userhost(), [entity.full()])
    global available_sem
    available_sem.run(process)

def unavailable_user(entity):
    users.remove(entity.userhost(), entity.full())

def resources(jid):
    """Find all watched resources for the given JID."""
    jids=users.users.get(jid, [])
    return [JID(j).resource for j in jids]

def online_users_count():
    return len(users.users) 

def _reset_all():
    global users
    global checker
    for u in users.users.values():
        u.clear()
        u.stop()
    users = UserRegistry()
    checker.reset()
    

def connected():
    _reset_all()

def disconnected():
    _reset_all()
