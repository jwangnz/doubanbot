import sys
import douban
import atom
from douban.service import DoubanService
from douban.client import OAuthClient
from twisted.internet import defer
from models import *
import dbb_config

class DoubanClient(object):
    
    def __init__(self): 
        pass

    @staticmethod
    def addBroadcasting(uid, key, secret, text):
        d = defer.Deferred()
        service = DoubanService(api_key=dbb_config.API_KEY, secret=dbb_config.API_SECRET)
        if not service.ProgrammaticLogin(key, secret):
            d.errback(ValueError("invalid access_key access_secret"))
            return d
        try:
            entry = douban.BroadcastingEntry() 
            entry.content = atom.Content(text = text)
            service.AddBroadcasting("/miniblog/saying", entry)
            d.callback(entry)
        except:
            d.errback(ValueError("send broadcasting failed"))
        finally:
            return d

    @staticmethod
    def getContactsBroadcasting1(uid, key, secret):
        d = defer.Deferred()
        service = DoubanService(api_key=dbb_config.API_KEY, secret=dbb_config.API_SECRET)
        if not service.ProgrammaticLogin(key, secret):
            d.errback(ValueError("invalid access_key access_secret"))
            return d
        uri = "/people/%s/miniblog/contacts" %uid
        try:
            feed = service.GetContactsBroadcastingFeed(uri)
            d.callback(feed)
        except:
            d.errback(ValueError("get contacts broadcasting failed"))
        finally:
            return d
        

    @staticmethod
    def getContactsBroadcasting(uid, key, secret):
        d = defer.Deferred()
        service = DoubanService(api_key=dbb_config.API_KEY, secret=dbb_config.API_SECRET)
        #print "key %s secret %s" %(dbb_config.API_KEY, dbb_config.API_SECRET)
        #print "access key %s secret %s" %(user.key, user.secret)
        if not service.ProgrammaticLogin(key, secret):
            d.errback(ValueError("invalid access_key access_secret"))
            return d
        # what the hell!
        uri = "/people/%s/miniblog/contacts" %uid.encode('utf-8')
        try: 
            feed = service.GetContactsBroadcastingFeed(uri)
            d.callback(feed)
        except:
            d.errback(ValueError("get contacts broadcasting failed"))
        finally:
            return d
    

if __name__ == '__main__':
    pass
