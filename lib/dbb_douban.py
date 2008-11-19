import sys
import douban
import atom
import gdata
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
        service = DoubanService(api_key=dbb_config.API_KEY, secret=dbb_config.API_SECRET)
        if not service.ProgrammaticLogin(key, secret):
            return False
        ret = False
        try:
            entry = douban.BroadcastingEntry()
            entry.content = atom.Content(text = text)
            service.AddBroadcasting("/miniblog/saying", entry)
            ret = True
        except gdata.service.RequestError, req :
            print "Error, addBroadcasting for user: %s failed, RequestError, code: %s, reason: %s, body: %s" %(uid, req[0]['status'], req[0]['reason'], req[0]['body'])   
        except:
            print "Error, addBroadcasting for user: %s failed, unexpected error" %uid
        finally:
            return ret

    @staticmethod
    def getContactsBroadcasting(uid, key, secret):
        service = DoubanService(api_key=dbb_config.API_KEY, secret=dbb_config.API_SECRET)
        if not service.ProgrammaticLogin(key, secret):
            return False
        uri = "/people/%s/miniblog/contacts" %uid.encode('utf-8')
        ret = False
        try:
            feed = service.GetContactsBroadcastingFeed(uri)
            ret = feed
        except gdata.service.RequestError, req:
            print "Error, getContactsBroadcasting for user: %s failed, RequestError, code: %s, reason: %s, body: %s" %(uid, req[0]['status'], req[0]['reason'], req[0]['body'])
        except:
            print "Error, getContactsBroadcasting for user: %s failed, unexpected error"
        finally:
            return ret
        
    

if __name__ == '__main__':
    pass
