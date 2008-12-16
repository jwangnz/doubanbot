import douban
import oauth
import atom
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
        hdef.addErrback(lambda e: deferred.errback(e))
        hdef.addCallback(lambda p: deferred.callback(parser(p)))
        return deferred

    def getBroadcasting(self, params=None):
        return self.__parsed(self.__get("/people/%s/miniblog" %self.uid), douban.BroadcastingFeedFromString)
    
    def getContactsBroadcasting(self, params=None):
        return self.__parsed(self.__get("/people/%s/miniblog/contacts" %self.uid), douban.BroadcastingFeedFromString)

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
