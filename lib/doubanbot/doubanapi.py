import re
import oauth
import atom
import gdata
import urllib
import douban
from twisted.internet import defer
from twisted.web import client

BASE_URL = 'http://api.douban.com'
API_KEY  = ''
API_SECRET = ''

TIMEOUT = 5

class Douban(object):

    agent = "twisted-douban - yet another knock-off douban client"

    def __init__(self, uid, key=None, secret=None):
        self.uid = uid
        self.key = key
        self.secret = secret
        self.consumer = oauth.OAuthConsumer(API_KEY, API_SECRET)
        if key and secret:
            self.token = oauth.OAuthToken(key, secret)
        else:
            self.token = None

    def __makeAuthHeader(self, method, url, parameters={}):
        headers = {}
        if self.token:
            oauth_request = oauth.OAuthRequest.from_consumer_and_token(self.consumer,
                    token=self.token, http_method=method, http_url=url, parameters=parameters)
            oauth_request.sign_request(oauth.OAuthSignatureMethod_HMAC_SHA1(), self.consumer, self.token)
            headers = oauth_request.to_header()

        if method in ('POST','PUT'):
            headers['Content-Type'] = 'application/atom+xml; charset=utf-8'
        
        for k, v in headers.iteritems():
            headers[k] = v.encode('utf-8')

        return headers

    def __urlencode(self, h):
        rv = []
        for k,v in h.iteritems():
            rv.append('%s=%s' %
                (urllib.quote(k.encode("utf-8")),
                urllib.quote(str(v).encode("utf-8"))))
        return '&'.join(rv)

    def __get(self, path, args=None):
        url = BASE_URL + path
        if args:
            url += '?' + self.__urlencode(args)

        return client.getPage(url, method='GET', timeout=TIMEOUT, agent=self.agent, headers=self.__makeAuthHeader('GET', url))

    def __post(self, path, data):
        h = {'Content-Type': 'application/atom+xml; charset=utf-8'}
        url = BASE_URL + path
        return client.getPage(url, method='POST', timeout=TIMEOUT, agent=self.agent,
            postdata=data, headers=self.__makeAuthHeader('POST', url, h))
    
    def __delete(self, path, args={}):
        url = BASE_URL + path
        return client.getPage(url, method='DELETE', timeout=TIMEOUT, agent=self.agent,
            postdata=self.__urlencode(args), headers=self.__makeAuthHeader('DELETE', url))

    def __parsed(self, hdef, parser):
        deferred = defer.Deferred()
        hdef.addCallbacks(
            callback=lambda p: deferred.callback(parser(str(p))),
            errback=lambda e: deferred.errback(e))
        return deferred

    def getBroadcasting(self, args=None):
        return self.__parsed(self.__get("/people/%s/miniblog" %self.uid, args), douban.BroadcastingFeedFromString)
    
    def getContactsBroadcasting(self, args=None):
        return self.__parsed(self.__get("/people/%s/miniblog/contacts" % str(self.uid), args), douban.BroadcastingFeedFromString)

    def addBroadcasting(self, content):
        entry = douban.BroadcastingEntry()
        entry.content = atom.Content(text=content) 
        return self.__parsed(self.__post("/miniblog/saying", entry.ToString()), douban.BroadcastingEntryFromString)

    def delBroadcasting(self, id):
        return self.__delete("/miniblog/%s" % str(id))
    
    def addRecommendation(self, title, url, comment=""):
        entry = douban.RecommendationEntry()
        entry.title = atom.Title(text=title)
        entry.link = atom.Link(href=url, rel="related")
        attribute = douban.Attribute('comment', comment)
        entry.attribute.append(attribute)
        return self.__parsed(self.__post("/recommendations", entry.ToString()), douban.RecommendationEntryFromString)

    def delRecommendation(self, id):
        return self.__delete("/recommendation/%s" % str(id))

    def getDoumailFeed(self, path, args=None):
        return self.__parsed(self.__get(path, args), douban.DoumailFeedFromString)

    def getDoumail(self, id, args=None):
        return self.__parsed(self.__get("/doumail/%s" % str(id), args), douban.DoumailEntryFromString)

    def addDoumail(self, to, subject, body, captacha_token=None, captacha_string=None):
        entry = douban.DoumailEntry() 
        receiverURI = "http://api.douban.com/people/%s" % to
        entry.entity.append(douban.Entity('receiver', "",extension_elements=[atom.Uri(text=receiverURI)]))
        entry.title = atom.Title(text=subject)
        entry.content = atom.Content(text=body)
        if captacha_token:
            entry.attribute.append(douban.Attribute('captacha_token', captacha_token))
        if captacha_string:
            entry.attribute.append(douban.Attribute('captacha_string', captacha_string))
        return self.__post("/doumails", entry.ToString())

def _entry_check(orig):
    def every(self):
        if not isinstance(self.entry, gdata.GDataEntry):
            return None
        else:
            return orig(self)
    return every

class Entry(object):

    def __init__(self, entry): 
        if isinstance(entry, gdata.GDataEntry):
            self.entry = entry
        else:
            self.entry = None

    @property
    @_entry_check
    def id(self):
        if hasattr(self.entry, 'id'):
            id = re.search('^.*\/(\d+)$', self.entry.id.text)
        if id:
            return int(id.group(1))
        return None

    @property
    @_entry_check
    def authorId(self):
        id = re.search('^.*\/(\d+)$', self.entry.author[0].uri.text)
        if id:
            return int(id.group(1))
        return None
        
    @property
    @_entry_check
    def authorName(self):
        return self.entry.author[0].name.text 

    @property
    @_entry_check
    def authorLink(self):
        return self.entry.author[0].uri.text.replace('api', 'www')
    
    @property
    @_entry_check
    def title(self):
        return self.entry.title.text

    @property
    @_entry_check
    def published(self):
        return self.entry.published.text.replace('T', ' ')[0:19]

    @property
    @_entry_check
    def contentLink(self):
        link = re.search('href=\"([^\"]+)\"', self.entry.content.text)
        if link and link.group(1):
            return link.group(1)
        return None

    @property
    @_entry_check
    def alternateLink(self):
        return self.entry.GetAlternateLink().href

    @property
    @_entry_check
    def isRead(self):
        if hasattr(self.entry, 'attribute'):
            for att in self.entry.attribute:
                if att.name == 'unread' and att.text:
                    return "false" == att.text
        return None

    @property
    @_entry_check
    def rating(self):
        if hasattr(self.entry, 'attribute'):
            for att in self.entry.attribute:
                if att.name == 'rating' and att.text: 
                    return att.text
        return None
        
    @property
    @_entry_check
    def comment(self):
        if hasattr(self.entry, 'attribute'):
            for att in self.entry.attribute:            
                if att.name == 'comment' and att.text:
                    return att.text

        return None

    @property
    @_entry_check
    def htmlContent(self):
        return self.entry.content.text


