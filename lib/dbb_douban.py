import sys, re
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
    def entryID(entry):
        if not isinstance(entry, gdata.GDataEntry):
            return False
        if hasattr(entry, 'id'):
            id = re.search('^.*\/(\d+)$', entry.id.text)
            if id:
                return id.group(1)
            else:
                print "Error: cannot get entry numeric id by regexp, entry: %s" %entry.id.text
        else:
            print "Error: the entry has no attribute: id"
        return False
            

    @staticmethod
    def delBroadcasting(uid, key, secret, id): 
        service = DoubanService(api_key=dbb_config.API_KEY, secret=dbb_config.API_SECRET)
        if not service.ProgrammaticLogin(key, secret):
            return False
        entry = douban.BroadcastingEntry()
        entry.id = atom.Id(text = "http://api.douban.com/miniblog/%s" %id.encode('utf-8'))
        try:
            ret = service.DeleteBroadcasting(entry)
        except gdata.service.RequestError, req: 
            print "Error, addBroadcasting for user: %s failed, RequestError, code: %s, reason: %s, body: %s" %(uid, req[0]['status'], req[0]['reason'], req[0]['body'])
        except:
            print "Error, delBroadcasting %s for user: %s failed, unexpected error" %(uid, id)
        finally:
            return ret
            
    
    @staticmethod
    def addBroadcasting(uid, key, secret, text):
        service = DoubanService(api_key=dbb_config.API_KEY, secret=dbb_config.API_SECRET)
        if not service.ProgrammaticLogin(key, secret):
            return False
        ret = False
        try:
            entry = douban.BroadcastingEntry()
            entry.content = atom.Content(text = text)
            feed = service.AddBroadcasting("/miniblog/saying", entry)
            if type(feed) is douban.BroadcastingEntry:
                ret = DoubanClient.entryID(feed)     
            else:
                print "Error: addBroadcasting returns unexpected result, type: %s" %type(feed)
                ret = False
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
            if req[0]['body'].find('Signature does not') != -1:
                ret = None
        except:
            print "Error, getContactsBroadcasting for user: %s failed, unexpected error"
        finally:
            return ret
        
    

if __name__ == '__main__':
    pass
