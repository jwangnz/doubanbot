#!/usr/bin/env python
import sys, os, inspect
path = os.path.dirname(inspect.currentframe().f_code.co_filename) or '.'
os.chdir(path)
sys.path.append(path)
sys.path.append(os.path.join(path, 'lib'))
import web, douban
from douban.service import DoubanService
from douban.client import OAuthClient
from models import *
from doubanbot import config

urls = (
 '[/]+', 'index',
 '/subscribe/([^\/]+)', 'subscribe',
 '/auth/([a-zA-Z0-9]{32})', 'auth',
 '/callback.*', 'callback',
)


class index:
    def GET(self):
        return """Welcome to Douban Bot.
Add douban@jabber.org to your gtalk/xmpp/jabber contacts, then you will get a setup instruction.
IM 'help' to the bot anytime you need help.

powered by GeoWHY.ORG
"""

class auth:
    def GET(self, hash):
        session = Session()
        try:
            authen = session.query(Authen).filter_by(hash=hash).one()
        except:
            return "hash %s not exists or expired" %hash
        
        try:
            user = session.query(User).filter_by(jid=authen.jid).one()
        except exc.NoResultFound, e:
            user = False
            return "user not found"
        if user and user.auth is True:
            return "user: %s jid: %s was already authenticated" %(user.uid, user.jid)
            
        client = OAuthClient(key=config.API_KEY, secret=config.API_SECRET)
        request_key, request_secret = client.get_request_token()
        if request_key and request_secret:
            try:
                token = Token(request_key, request_secret, hash)
                session.add(token)
                session.commit()
            #except:
            #    return web.internalerror()
            finally:
                session.close()
            url = client.get_authorization_url(request_key, request_secret, callback=config.AUTH_CALLBACK)
            return web.TempRedirect(url)
        else:
            return "request request_key failed"

class callback:
    def GET(self):
        client = OAuthClient(key=config.API_KEY, secret=config.API_SECRET)
        request_key = web.input().get('oauth_token', False)
        session = Session()
        if request_key:
            try:
                token = session.query(Token).filter_by(key=request_key).one()
            except exc.NoResultFound, e: 
                return "request token: %s not found" %request_key
        else:
            return web.internalerror()
        client = OAuthClient(key=config.API_KEY, secret=config.API_SECRET)
        access_key, access_secret = client.get_access_token(request_key, token.secret)
        if not access_key or not access_secret:
            return "Error: access_key: %s access_token: %s" %(access_key, access_secret)
        
	    print "access_key %s, access_secret %s" %(access_key, access_secret)
        service = DoubanService(api_key=config.API_KEY, secret=config.API_SECRET)
        
        if not service.ProgrammaticLogin(access_key, access_secret):
            return "service login failed"

        try:
            people = service.GetAuthorizedUID('/people/@me')
        except:
            return web.internalerror()
        try:
            authen = session.query(Authen).filter_by(hash=token.hash).one()
        except:
            return web.internalerror()
        if not authen.jid:
            return "jid not found"


        try:
            user = session.query(User).filter_by(jid=authen.jid).one()
            user.uid = people.uid.text
        except:
            user = User()
        user.jid = authen.jid
        user.uid = people.uid.text
        user.name = people.title.text
        user.auth = True
        user.key = access_key
        user.secret = access_secret
        try:
            session.add(user)
            session.commit()
        except:
            return "insert user failed"
        return "OK, authorization of user: %s, jid: %s finished.\nIM 'help' to the bot to see what you can do. enjoy it!" %(user.uid, user.jid)

class subscribe:
    def GET(self, jid):
        return 'you cannot use this'
        session = Session()
        hash = Authen.get_authen_code(jid, session)
        if hash is False:
            hash = Authen.gen_authen_code(jid, session)
        if hash is False:
            return "fail %s" %hash
        raise web.seeother("%s/%s" %(config.AUTH_URL, hash))

application = web.application(urls, globals()).wsgifunc()
