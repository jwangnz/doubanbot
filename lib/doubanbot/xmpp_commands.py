from __future__ import with_statement

import time
import datetime
import re
import chardet
import sre_constants
import urlparse

from twisted.python import log
from twisted.internet import defer
from twisted.words.xish import domish
from twisted.words.protocols.jabber.jid import JID
from twisted.web import client
from sqlalchemy.orm import exc

import models
import config
import doubanapi
import scheduling
import protocol

all_commands={}

def arg_required(validator=lambda n: n):
    def f(orig):
        def every(self, user, prot, args, session):
            if validator(args):
                orig(self, user, prot, args, session)
            else:
                prot.send_plain(user.jid, "Arguments required for %s:\n%s"
                    % (self.name, self.extended_help))
        return every
    return f

def oauth_required(orig):
    def every(self, user, prot, args, session):
        if user.auth is True:
            orig(self, user, prot, args, session)
        else:
            hash = models.Authen.gen_authen_code(user.jid, session)
            link = "%s/%s" %(config.AUTH_URL, hash)
            message = "Please use the link below to authorize the bot for fetching your douban data:\n%s" %link
            prot.send_plain(user.jid, "You must authorization the bot before calling %s\n%s"
                % (self.name, message))
    return every

def admin_required(orig):
    def every(self, user, prot, args, session):
        if user.is_admin:
            orig(self, user, prot, args, session)
        else:
            prot.send_plain(user.jid, "You're not an admin.")
    return every

class BaseCommand(object):
    """Base class for command processors."""

    def __get_extended_help(self):
        if self.__extended_help:
            return self.__extended_help
        else:
            return self.help

    def __set_extended_help(self, v):
        self.__extended_help=v

    extended_help=property(__get_extended_help, __set_extended_help)

    def __init__(self, name, help=None, extended_help=None, aliases=[]):
        self.name=name
        self.help=help
        self.aliases = aliases
        self.extended_help=extended_help

    @oauth_required
    def __call__(self, user, prot, args, session):
        raise NotImplementedError()

    def is_a_url(self, u):
        try:
            parsed = urlparse.urlparse(str(u))
            return parsed.scheme in ['http', 'https'] and parsed.netloc
        except:
            return False

class ReauthCommand(BaseCommand):

    def __init__(self):
        super(ReauthCommand, self).__init__('reauth', 'Re Authorize the bot.', aliases=['auth'])

    def __call__(self, user, prot, args, session):
        hash = models.Authen.gen_authen_code(user.jid, session)
        link = "%s/%s" %(config.AUTH_URL, hash)
        message = "Please use the link below to authorise the bot for fetching your douban data:\n%s" %link
        try:
            prot.send_plain(user.jid, message)
            user.auth = False
            user.key = None
            user.secret = None 
            session.add(user)
            session.commit()
            scheduling.disable_user(user.jid)
        except:
            log.msg(":(, reauth user: user.jid failed")

class BaseStatusCommand(BaseCommand):

    def get_user_status(self, user):
        rv = []
        rv.append("Jid:  %s" % user.jid)
        rv.append("Notification status: %s"
            % {True: 'Active', False: 'Inactive'}[user.active])
        rv.append("Autopost status: %s"
            % {True: 'Active', False: 'Inactive'}[user.auto_post])
        rv.append("Douban OAuth status: %s"
            % {True: 'Active', False: 'Inactive'}[user.auth])
        resources = scheduling.resources(user.jid)
        if resources:
            rv.append("I see you logged in with the following resources:")
            for r in resources:
                rv.append(" %s %s" % ('\xe2\x80\xa2'.decode('utf-8'), r))
        else:
            rv.append("I don't see you logged in with any resource I'd send "
                "a message to.  Perhaps you're dnd, xa, or negative priority.")
        if user.is_quiet():
            rv.append("All alerts are quieted until %s" % str(user.quiet_until))
        if user.is_admin:
            with models.Session() as session:
                auth_user = session.query(models.User).filter_by(auth=True).count()
                rv.append("Authorized user: %s" %auth_user)
                auth_active_user = session.query(models.User).filter_by(auth=True).filter_by(active=True).count()
                rv.append("Active user: %s" %auth_active_user) 
                online_user = scheduling.online_users_count()
                rv.append("Online user: %s" %online_user)
        return "\n".join(rv)

class StatusCommand(BaseStatusCommand):
    
    def __init__(self):
        super(StatusCommand, self).__init__('status', 'Check your status.')

    @oauth_required
    def __call__(self, user, prot, args, session):
        prot.send_plain(user.jid, self.get_user_status(user))


class HelpCommand(BaseCommand):

    def __init__(self):
        super(HelpCommand, self).__init__('help', 'You need help.', aliases=['?'])

    @oauth_required
    def __call__(self, user, prot, args, session):
        rv=[]
        if args and args.strip():
            c=all_commands.get(args.strip().lower(), None)
            if c:
                rv.append("Help for %s:\n" % c.name)
                rv.append(c.extended_help)
                if c.aliases:
                    rv.append("\nAliases:\n * " +
                        "\n * ".join(c.aliases))
            else:
                rv.append("Unknown command %s." % args)
        else:
            for k in sorted(all_commands.keys()):
                if (not k.startswith('adm_')) or user.is_admin:
                    rv.append('%s\t%s' % (k, all_commands[k].help))
            rv.append("\nPlease post questions, suggestions or complaints at http://www.douban.com/group/doubot/")
        prot.send_plain(user.jid, "\n".join(rv))


class RecommendationCommand(BaseCommand):
    def __init__(self):
        super(RecommendationCommand, self).__init__('reco', 'Recommend a url')
        self.extended_help="""Usage: reco title url comment
title and comment are optional
"""
    

    def _posted(self, entry, args, uid, jid, prot):
        entry = doubanapi.Entry(entry)
        prot.send_plain(jid, ":) Your recommendation: '%s' has been posted, you could use command: 'delete R%s' to delete it"
            % (args, str(entry.id)))

    def _failed(self, e, args, uid, jid, prot):
        log.msg("Error post recommendation for %s: %s" % (jid, e.getErrorMessage()))
        prot.send_plain(jid, ":( Failed to post recommendation: '%s', maybe douban.com has problem now." % (args))

    def _getTitleFailed(self, e, url, uid, jid, prot):
        log.msg("Error get title of '%s': %s" % (url, e.getErrorMessage()))
        prot.send_plain(jid, ":( failed get title of '%s', %s" % (url, e.getErrorMessage()))

    def _encode(self, char):
        return char.decode(chardet.detect(char)['encoding']).encode('utf-8')

    def _parseHTMLTitle(self, page):
        re.IGNORECASE = True
        match = re.search('.*[^\<]+\<title\>([^\>^\<]+)\<\/title\>.*', str(page))
        if match:
            return self._encode(match.group(1))
        else:
            return None

    def _getPageTitle(self, url, title=None):
        if title:
            return defer.succeed(title)
        else:
            deferred = defer.Deferred()
            client.getPage(str(url), timeout=5).addCallback(
                lambda p: deferred.callback(self._parseHTMLTitle(p))).addErrback(
                lambda e: deferred.errback(e))
            return deferred

    def _postRecommendation(self, title, url, comment, uid, key, secret, jid, args, prot):
        if not title:
            return self._getTitleFailed(self, "Empty title", url, uid, jid, prot)
        doubanapi.Douban(uid, key, secret).addRecommendation(title, url, comment).addCallback(
            self._posted, args, uid, jid, prot).addErrback(
            self._failed, args, uid, jid, prot)

    @arg_required()
    @oauth_required
    def __call__(self, user, prot, args, session):
        if args:
            re.IGNORECASE = True
            match = re.search('^(\S*)\s*(http|https)(\:\/\/[^\/]\S+)\s*(.*)$', args)
            if not match:
                return prot.send_plain(user.jid, "Error, parameter error. see 'help reco'")

            title = match.group(1)
            url = "%s%s" % (match.group(2), match.group(3))
            comment = match.group(4)
            uid = user.uid
            key = user.key
            jid = user.jid
            secret = user.secret
            self._getPageTitle(url, title).addCallbacks(
                callback=lambda t: self._postRecommendation(t, url, comment, uid, key, secret, jid, args, prot),
                errback=lambda e: self._getTitleFailed(e, url, uid, jid, prot))
    

class PostCommand(BaseCommand):
    def __init__(self):
        super(PostCommand, self).__init__('post', 'Post a message.', aliases=['say'])

    def _posted(self, entry, args, jid, uid, prot):
        id = doubanapi.Entry(entry).id
        prot.send_plain(jid, ":) Your message: '%s' has been posted, you could use command: 'delete B%s' to delete it"
            % (args, id))

    def _failed(self, e, args, jid, uid, prot):
        log.msg("Error post messge for %s:  %s" % (jid, e.getErrorMessage()))
        prot.send_plain(jid, ":( Failed to post message: '%s', maybe douban.com has problem now." % (args))

    @oauth_required
    @arg_required()
    def __call__(self, user, prot, args, session):
        if args:
            uid = user.uid
            key = user.key
            secret = user.secret
            if key and secret and uid:
                jid = user.jid 
                doubanapi.Douban(uid, key, secret).addBroadcasting(args).addCallback(
                    self._posted, args, jid, uid, prot).addErrback(self._failed, args, jid, uid, prot)
        else:
            prot.send_plain(user.jid, "You say nothing :(")

class DeleteCommand(BaseCommand):
    def __init__(self):
        super(DeleteCommand, self).__init__('delete', 'Delete broadcasting/recommendation.')

    def _posted(self, result, jid, args, prot):
        prot.send_plain(jid, ":) item: %s has been deleted" % args)
        
    def _failed(self, e, jid, args, prot):
        log.msg("Error delete item %s: %s" % (args, e.getErrorMessage()))
        prot.send_plain(jid, ":( failed delete item: %s, %s" % (args, e.getErrorMessage()) )

    @oauth_required
    @arg_required()
    def __call__(self, user, prot, args, session):
        if args:
            args = args.strip().upper()
            match = re.search('^([RB])(\d+)$', args)
            if not match:
                return prot.send_plain(user.jid, ":( invalid id for delete")
            type = match.group(1) 
            if type == 'R': name = 'recommendation'
            else: name = 'broadcasting'
            id = int(match.group(2))
            uid = user.uid
            key = user.key
            jid = user.jid
            secret = user.secret
            if 'recommendation' == name:
                doubanapi.Douban(uid, key, secret).delRecommendation(id).addCallback(
                    self._posted, jid, args, prot).addErrback(self._failed, jid, args, prot)
            else:
                doubanapi.Douban(uid, key, secret).delBroadcasting(id).addCallback(
                    self._posted, jid, args, prot).addErrback(self._failed, jid, args, prot)

        else:
            prot.send_plain(user.jid, ":( You should specify the id for deletion")

class OnCommand(BaseCommand):
    def __init__(self):
        super(OnCommand, self).__init__('on', 'Enable notify.')

    def __call__(self, user, prot, args, session):
        user.active=True
        scheduling.enable_user(user.jid)
        prot.send_plain(user.jid, "Notify enabled.")

class OffCommand(BaseCommand):
    def __init__(self):
        super(OffCommand, self).__init__('off', 'Disable notify.')

    def __call__(self, user, prot, args, session):
        user.active=False
        scheduling.disable_user(user.jid)
        prot.send_plain(user.jid, "Notify disabled.")

def must_be_on_or_off(args):
    return args and args.lower() in ["on", "off"]
 
class AutopostCommand(BaseCommand):
 
    def __init__(self):
        super(AutopostCommand, self).__init__('autopost',
            "Enable or disable autopost.")
 
    @oauth_required
    @arg_required(must_be_on_or_off)
    def __call__(self, user, prot, args, session):
        user.auto_post = (args.lower() == "on")
        prot.send_plain(user.jid, "Autoposting is now %s." % (args.lower()))

class QuietCommand(BaseCommand):
    def __init__(self):
        super(QuietCommand, self).__init__('quiet', 'Temporarily quiet broadcastings.')
        self.extended_help="""Quiet alerts for a period of time.

Available time units:  m, h, d

Example, quiet for on hour:
  quiet 1h
"""

    @oauth_required
    @arg_required()
    def __call__(self, user, prot, args, session):
        if not args:
            prot.send_plain(user.jid, "How long would you like me to be quiet?")
            return
        m = {'m': 1, 'h': 60, 'd': 1440}
        parts=args.split(' ', 1)
        time=parts[0]
        match = re.compile(r'(\d+)([hmd])').match(time)
        if match:
            t = int(match.groups()[0]) * m[match.groups()[1]]
            u=datetime.datetime.now() + datetime.timedelta(minutes=t)

            user.quiet_until=u
            scheduling.disable_user(user.jid)
            prot.send_plain(user.jid,
                "You won't hear from me again until %s" % str(u))
        else:
            prot.send_plain(user.jid, "I don't understand how long you want "
                "me to be quiet.  Try: quiet 5m")

class AdminUserStatusCommand(BaseStatusCommand):
 
    def __init__(self):
        super(AdminUserStatusCommand, self).__init__('adm_status',
            "Check a user's status.")
 
    @admin_required
    @arg_required()
    def __call__(self, user, prot, args, session):
        try:
            u=models.User.by_jid(args, session)
            prot.send_plain(user.jid, self.get_user_status(u))
        except Exception, e:
            prot.send_plain(user.jid, "Failed to load user: " + str(e))

class AdminSubscribeCommand(BaseCommand):
 
    def __init__(self):
        super(AdminSubscribeCommand, self).__init__('adm_subscribe',
            'Subscribe a user.')
 
    @admin_required
    @arg_required()
    def __call__(self, user, prot, args, session):
        prot.send_plain(user.jid, "Subscribing " + args)
        protocol.presence_conn.subscribe(JID(args))

class AdminRequestAuthCommand(BaseCommand):

    def __init__(self):
        super(AdminRequestAuthCommand, self).__init__('adm_auth',
            "Send authorization request to a user.")

    @admin_required
    @arg_required()
    def __call__(self, user, prot, args, session):
        hash = models.Authen.gen_authen_code(args, session)
        link = "%s/%s" %(config.AUTH_URL, hash)
        message = "Please use the link below to authorize the bot for fetching your douban data:\n%s" %link
        prot.send_plain(user.jid, "Sending authorization request to " + args)
        prot.send_plain(args, message)

for __t in (t for t in globals().values() if isinstance(type, type(t))):
    if BaseCommand in __t.__mro__:
        try:
            i =  __t()
            all_commands[i.name] = i
        except TypeError, e:
            log.msg("Error loading %s: %s" % (__t.__name__, str(e)))
            pass
