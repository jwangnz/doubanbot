import re
import oauth
import atom
import gdata
import douban
from twisted.internet import defer
from twisted.web import client

BASE_URL = 'http://api.douban.com'
API_KEY  = ''
API_SECRET = ''

class Douban(object):

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
                urllib.quote(v.encode("utf-8"))))
        return '&'.join(rv)

    def __get(self, path, args=None):
        url = BASE_URL + path
        if args:
            url += '?' + self.__urlencode(args)

        return client.getPage(url, method='GET', headers=self.__makeAuthHeader('GET', url))

    def __post(self, path, data):
        h = {'Content-Type': 'application/atom+xml; charset=utf-8'}
        url = BASE_URL + path
        return client.getPage(url, method='POST',
            postdata=data, headers=self.__makeAuthHeader('POST', url, h))
    
    def __delete(self, path, args={}):
        url = BASE_URL + path
        return client.getPage(url, method='DELETE',
            postdata=self.__urlencode(args), headers=self.__makeAuthHeader('DELETE', url))

    def __parsed(self, hdef, parser):
        deferred = defer.Deferred()
        hdef.addCallbacks(
            callback=lambda p: deferred.callback(parser(str(p))),
            errback=lambda e: deferred.errback(e))
        return deferred

    def getBroadcasting(self, params=None):
        return self.__parsed(self.__get("/people/%s/miniblog" %self.uid), douban.BroadcastingFeedFromString)
    
    def getContactsBroadcasting(self, params=None):
        return self.__parsed(self.__get("/people/%s/miniblog/contacts" % str(self.uid)), douban.BroadcastingFeedFromString)

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
            return id.group(1) 
        return None

    @property
    @_entry_check
    def authorId(self):
        # can't get it in atom.Author, shit 
        pass
        
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
    def link(self):
        link = re.search('href=\"([^\"]+)\"', self.entry.content.text)
        if link and link.group(1):
            return link.group(1)
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


