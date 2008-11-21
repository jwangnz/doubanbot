import time
import datetime
import re
import sre_constants

from twisted.words.xish import domish
from twisted.internet import threads
from sqlalchemy.orm import exc
from dbb_douban import DoubanClient

import models
import dbb_config

all_commands={}

def __register(cls):
    c=cls()
    all_commands[c.name]=c

class CountingFile(object):
    """A file-like object that just counts what's written to it."""
    def __init__(self):
        self.written=0
    def write(self, b):
        self.written += len(b)
    def close(self):
        pass
    def open(self):
        pass
    def read(self):
        return None

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

    def __init__(self, name, help=None, extended_help=None):
        self.name=name
        self.help=help
        self.extended_help=extended_help

    def __call__(self, user, prot, args, session):
        raise NotImplementedError()

    def is_a_url(self, u):
        try:
            s=str(u)
            # XXX:  Any good URL validators?
            return True
        except:
            return False

class ArgRequired(BaseCommand):

    def __call__(self, user, prot, args, session):
        if self.has_valid_args(args):
            self.process(user, prot, args, session)
        else:
            prot.send_plain(user.jid_full, "Arguments required for %s:\n%s"
                % (self.name, self.extended_help))

    def has_valid_args(self, args):
        return args

    def process(self, user, prot, args, session):
        raise NotImplementedError()

class WatchRequired(BaseCommand):

    def __call__(self, user, prot, args, session):
        if self.has_valid_args(args):
            a=args.split(' ', 1)
            newarg=None
            if len(a) > 1: newarg=a[1]
            try:
                watch=session.query(models.Watch).filter_by(
                    url=a[0]).filter_by(user_id=user.id).one()
                self.process(user, prot, watch, newarg, session)
            except exc.NoResultFound:
                prot.send_plain(user.jid_full, "Cannot find watch for %s" % a[0])
        else:
            prot.send_plain(user.jid_full, "Arguments required for %s:\n%s"
                % (self.name, self.extended_help))

    def has_valid_args(self, args):
        return self.is_a_url(args)

    def process(self, user, prot, watch, args, session):
        raise NotImplementedError()

class ReauthCommand(BaseCommand):
    
    def __init__(self):
        super(ReauthCommand, self).__init__('reauth', 'Re Authorise.')

    def __call__(self, user, prot, args, session):
        hash = models.Authen.gen_authen_code(user.jid, session)
        link = "%s/%s" %(dbb_config.AUTH_URL, hash)
        message = "Please use the link below to authorise the bot for fetching your douban data:\n%s" %link
        try:
            prot.send_plain(user.jid_full, message)
            user.auth = False
            session.add(user)
            session.commit()
        except:
            print "Oops, reauth user: user.jid failed" 

__register(ReauthCommand)


class StatusCommand(BaseCommand):

    def __init__(self):
        super(StatusCommand, self).__init__('status', 'Check your status.')

    def __call__(self, user, prot, args, session):
        rv=[]
        rv.append("Jid:  %s" % user.jid)
        rv.append("Jabber status:  %s" % user.status)
        rv.append("Notify status:  %s"
            % {True: 'Active', False: 'Inactive'}[user.active])
        if user.is_quiet():
            rv.append("All alerts are quieted until %s" % str(user.quiet_until))
        if user.jid in dbb_config.ADMINS:
            auth_user = session.query(models.User).filter_by(auth=True).count()
            rv.append("Authorized user: %s" %auth_user)
        prot.send_plain(user.jid_full, "\n".join(rv))

__register(StatusCommand)


class HelpCommand(BaseCommand):

    def __init__(self):
        super(HelpCommand, self).__init__('help', 'You need help.')

    def __call__(self, user, prot, args, session):
        rv=[]
        if args:
            c=all_commands.get(args.strip().lower(), None)
            if c:
                rv.append("Help for %s:\n" % c.name)
                rv.append(c.extended_help)
            else:
                rv.append("Unknown command %s." % args)
        else:
            for k in sorted(all_commands.keys()):
                rv.append('%s\t%s' % (k, all_commands[k].help))
        prot.send_plain(user.jid_full, "\n".join(rv))

__register(HelpCommand)

class RecommendationCommand(ArgRequired):
    def __init__(self):
        super(RecommendationCommand, self).__init__('reco', 'Recommendation something.')
        
    def process(self, user, prot, args, session):
        if args:
            re.IGNORECASE = True
            match = re.search('^(.+)\s(http|https)(\:\/\/[^\/]\S+)(.*)$', args)
            re.IGNORECASE = False
            if not match:
                return prot.send_plain(user.get_jid_full(), "Error, parameter after command 'reco' should be format of: title url comment") 
            title = match.group(1)
            url = "%s%s" %(match.group(2), match.group(3))
            comment = match.group(4)
            jid_full = user.get_jid_full()
            uid = user.uid
            key = user.key
            secret = user.secret
            def callback(value): 
                if value:
                    prot.send_plain(jid_full, "OK, recommendation %s: '%s' added.\nyou could use command: 'delete %s' to delete it" %(value, args, value))
                else:
                    prot.send_plain(jid_full, "Oops, add recommendation: %s failed" %args)
            def add():
                return DoubanClient.addRecommendation(uid, key, secret, title, url, comment)
            d = threads.deferToThread(add)
            d.addCallback(callback)
            return d
        else:
            prot.send_plain(jid_full, "You recommendate nothing :(")

__register(RecommendationCommand)

class SayCommand(ArgRequired):
    def __init__(self):
        super(SayCommand, self).__init__('say', 'Say something.')

    def process(self, user, prot, args, session):
        if args:
            jid_full = user.get_jid_full()
            uid = user.uid
            key = user.key
            secret = user.secret
            def callback(value):
                if value:
                    prot.send_plain(jid_full, "OK, miniblog %s: '%s' added.\nyou could use command: 'delete %s' to delete it" %(value, args, value))
                else:
                   prot.send_plain(jid_full, "Oops, send: %s failed" %args) 
            def add():
                return DoubanClient.addBroadcasting(uid, key, secret, args)
            d = threads.deferToThread(add)
            d.addCallback(callback)
        else:
            prot.send_plain(user.get_jid_full(), "You say nothing :(")

__register(SayCommand)

class DeleteCommand(ArgRequired):
    def __init__(self):
        super(DeleteCommand, self).__init__('delete', 'Delete broadcasting/recommendation.')

    def process(self, user, prot, args, session):
        if args:
            args = args.strip().upper()
            match = re.search('^([RB])(\d+)$', args)
            if not match:
                return prot.send_plain(user.get_jid_full(), "Oops, invalid id for delete")
            type = match.group(1) 
            if type == 'R': name = 'recommendation'
            else: name = 'broadcasting'
            id = match.group(2)
            jid_full = user.get_jid_full()
            uid = user.uid
            key = user.key
            secret = user.secret
            def callback(value):
                if value:
                    prot.send_plain(jid_full, "OK, %s %s deleted" %(name, args))
                else: 
                    prot.send_plain(jid_full, "Oops, delete %s %s failed" %(name, args))

            def delete():
                if type == 'B':
                    return DoubanClient.delBroadcasting(uid, key, secret, id)
                else:
                    return DoubanClient.delRecommendation(uid, key, secret, id)
            d = threads.deferToThread(delete)
            d.addCallback(callback)
        else:
            prot.send_plain(user.get_jid_full(), "You should specify the id for deletion")

__register(DeleteCommand)

class OnCommand(BaseCommand):
    def __init__(self):
        super(OnCommand, self).__init__('on', 'Enable notify.')

    def __call__(self, user, prot, args, session):
        user.active=True
        prot.send_plain(user.jid_full, "Notify enabled.")

__register(OnCommand)

class OffCommand(BaseCommand):
    def __init__(self):
        super(OffCommand, self).__init__('off', 'Disable notify.')

    def __call__(self, user, prot, args, session):
        user.active=False
        prot.send_plain(user.jid_full, "Notify disabled.")

__register(OffCommand)

class QuietCommand(ArgRequired):
    def __init__(self):
        super(QuietCommand, self).__init__('quiet', 'Temporarily quiet broadcastings.')
        self.extended_help="""Quiet alerts for a period of time.

Available time units:  m, h, d

Example, quiet for on hour:
  quiet 1h
"""

    def process(self, user, prot, args, session):
        if not args:
            prot.send_plain(user.jid_full, "How long would you like me to be quiet?")
            return
        m = {'m': 1, 'h': 60, 'd': 1440}
        parts=args.split(' ', 1)
        time=parts[0]
        match = re.compile(r'(\d+)([hmd])').match(time)
        if match:
            t = int(match.groups()[0]) * m[match.groups()[1]]
            u=datetime.datetime.now() + datetime.timedelta(minutes=t)

            user.quiet_until=u
            prot.send_plain(user.jid_full,
                "You won't hear from me again until %s" % str(u))
        else:
            prot.send_plain(user.jid_full, "I don't understand how long you want "
                "me to be quiet.  Try: quiet 5m")

__register(QuietCommand)
