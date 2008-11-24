import sys, re
import atom
import gdata
import douban
from douban.service import DoubanService
from douban.client import OAuthClient
from twisted.internet import defer
from models import *
from doubanbot import config

class DoubanClient(object):

    def __init__(self):
        pass

    @staticmethod
    def entryID(entry, prefix = ''):
        if not isinstance(entry, gdata.GDataEntry):
            return False
        if hasattr(entry, 'id'):
            id = re.search('^.*\/(\d+)$', entry.id.text)
            if id:
                return prefix + id.group(1)
            else:
                print "Error: cannot get entry numeric id by regexp, entry: %s" %entry.id.text
        else:
            print "Error: the entry has no attribute: id"
        return False

    @staticmethod
    def addRecommendation(uid, key, secret, title, url, comment=""):
        service = DoubanService(api_key=config.API_KEY, secret=config.API_SECRET)
        if not service.ProgrammaticLogin(key, secret):
            return False
        ret = False
        try:
            print "before add reco"
            entry = service.AddRecommendation(title, url, comment)
            print "after add reco"
            if type(entry) is douban.RecommendationEntry: 
                ret = DoubanClient.entryID(entry, 'R')
        except gdata.service.RequestError, req:
            print "Error, addRecommendation for user: %s failed, RequestError, code: %s, reason: %s, body: %s" %(uid, req[0]['status'], req[0]['reason'], req[0]['body'])
        except:
            print "Error, addRecommendation title: %s url: %s coment: %s" %(url, comment)
        finally:
            return ret
    
    @staticmethod
    def delRecommendation(uid, key, secret, id):
        service = DoubanService(api_key=config.API_KEY, secret=config.API_SECRET)
        if not service.ProgrammaticLogin(key, secret):
            return False
        ret = False
        try:
            entry = douban.RecommendationEntry()
            entry.id = atom.Id(text = "http://api.douban.com/recommendation/%s" %id.encode('utf-8'))
            ret = service.DeleteRecommendation(entry)
        except gdata.service.RequestError, req:
            print "Error, delRecommendation for user: %s failed, RequestError, code: %s, reason: %s, body: %s" %(uid, req[0]['status'], req[0]['reason'], req[0]['body'])
        except:
            print "Error, delRecommendation %s for user: %s failed, unexpected error" %(id, uid)
        finally:
            return ret

    @staticmethod
    def delBroadcasting(uid, key, secret, id):
        service = DoubanService(api_key=config.API_KEY, secret=config.API_SECRET)
        if not service.ProgrammaticLogin(key, secret):
            return False
        ret = False
        entry = douban.BroadcastingEntry()
        entry.id = atom.Id(text = "http://api.douban.com/miniblog/%s" %id.encode('utf-8'))
        try:
            ret = service.DeleteBroadcasting(entry)
        except gdata.service.RequestError, req: 
            print "Error, delBroadcasting for user: %s failed, RequestError, code: %s, reason: %s, body: %s" %(uid, req[0]['status'], req[0]['reason'], req[0]['body'])
        except:
            print "Error, delBroadcasting %s for user: %s failed, unexpected error" %(id, uid)
        finally:
            return ret


    @staticmethod
    def addBroadcasting(uid, key, secret, text):
        service = DoubanService(api_key=config.API_KEY, secret=config.API_SECRET)
        if not service.ProgrammaticLogin(key, secret):
            return False
        ret = False
        try:
            entry = douban.BroadcastingEntry()
            entry.content = atom.Content(text = text)
            feed = service.AddBroadcasting("/miniblog/saying", entry)
            if type(feed) is douban.BroadcastingEntry:
                ret = DoubanClient.entryID(feed, 'B') 
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
        service = DoubanService(api_key=config.API_KEY, secret=config.API_SECRET)
        if not service.ProgrammaticLogin(key, secret):
            return False
        uri = "/people/%s/miniblog/contacts" %uid.encode('utf-8')
        ret = False
        try:
            feed = service.GetContactsBroadcastingFeed(uri)
            ret = feed
        except gdata.service.RequestError, req:
            print "Error, getContactsBroadcasting for user: %s failed, RequestError, code: %s, reason: %s, body: %s" %(uid, req[0]['status'], req[0]['reason'], req[0]['body'])
            if req[0]['body'].find('no auth') != -1:
                ret = None
        except:
            print "Error, getContactsBroadcasting for user: %s failed, unexpected error"
        finally:
            return ret



if __name__ == '__main__':
    pass
