import re
import datetime
import douban

import models
import config
import doubanapi
import protocol

from twisted.python import log
from twisted.internet import defer, threads, task
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
        session.commit()

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

                plain = "[New Mail]\nFrom: %s\nDate: %s\nTitle: %s\nView: %s\n" % (
                    entry.authorName.decode('utf-8'), entry.published,
                    entry.title.decode('utf-8'), entry.alternateLink)
                plains.append(plain)

        if len(plains) > 0: 
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
                link = entry.link
                if link:
                    plain += " %s" % entry.link
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
            errback=lambda feed: self.reportError(err))         

    def _reportError(self, e):
        log.msg("Error getting user data for %s: %s" % (self.short_jid, str(e)))

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
            if (u[0] and u[1] and u[2] and u[3]):
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

    def set_creds(self, short_jid, uid, name, key, secret):
        u = self.users.get(short_jid)
        if not u:
            log.msg("Couldn't find %s to set creds" % short_jid)
            return

        u.uid = uid
        u.name = name
        u.key = key
        u.secret = secret
        available = u.uid and u.key and u.secret

        global checker
        if not available:
            checker.add(short_jid)
        else:
            checker.remove(short_jid)

        if available and not u.loop:
            u.start()
        elif u.loop and not available:
            u.stop()

    def remove(self, short_jid, full_jid=None):
        q = self.users.get(short_jid)
        if not q:
            return
        q.discard(full_jid)
        if not q:
            def unavailableUser(p):
                q.stop()
                del self.users[short_jid]
            threads.deferToThread(q._deferred_write, short_jid, 'status', 'unavailable').addCallback(unavailableUser)

users = UserRegistry()
checker = RoutinChecker()

def _entity_to_jid(entity):
    return entity if isinstance(entity, basestring) else entity.userhost()

@models.wants_session
def _load_user(entity, session):
    u = models.User.update_status(_entity_to_jid(entity), None, session)
    if u.active is False or u.auth is False or u.is_quiet():
        return ('', '', '', '', u.last_cb_id, u.last_dm_id)
    return (u.uid, u.name, u.key, u.secret, u.last_cb_id, u.last_dm_id)

def _init_user(u, short_jid, full_jids):
    if u:
        for j in full_jids:
            users.add(short_jid, j, u[4], u[5])
        users.set_creds(short_jid, u[0], u[1], u[2], u[3])

def enable_user(jid):
    def process():
        return threads.deferToThread(_load_user, jid).addCallback(
            _init_user, jid, users.users.get(jid, []))
    global available_sem
    available_sem.run(process)

def disable_user(jid):
    users.set_creds(jid, None, None, None, None)

def available_user(entity):
    def process():
        return threads.deferToThread(_load_user, entity).addCallback(
            _init_user, entity.userhost(), [entity.full()])
    global available_sem
    available_sem.run(process)

def unavailable_user(entity):
    users.remove(entity.userhost(), entity.full())

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
