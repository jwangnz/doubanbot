#!/usr/bin/env python
import sys
import os
import web, douban
from douban.service import DoubanService
from douban.client import OAuthClient
from models import *

urls = (
 '/douban/', 'index',
 '/douban/subscribe/([^\/]+)', 'subscribe',
 '/douban/auth/([a-zA-Z0-9]{32})', 'auth',
 '/douban/callback.*', 'callback',
)

API_KEY=config.API_KEY
SECRET=config.API_SECRET
TOKEN_KEY=''
TOKEN_SECRET=''
PREFIX=''


class index:
    def GET(self):
        return 'Hey You! Whats up!'

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
            return "DDDDDDDDDDD"
        if user and user.auth is True:
            return "user: %s jid: %s was already authenticated" %(user.uid, user.jid)
            
        # start the oauth process
        client = OAuthClient(key=API_KEY, secret=SECRET) 
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
            url = client.get_authorization_url(request_key, request_secret, callback=config.AUTH_URL +'/callback')
            return web.TempRedirect(url)
        else:
            return "request request_key failed"

class callback:
    def GET(self):
        client = OAuthClient(key=API_KEY, secret=SECRET) 
        request_key = web.input().get('oauth_token', False) 
        print ">> callback token: %s" %request_key
        session = Session()
        if request_key:
            try:
                token = session.query(Token).filter_by(key=request_key).one()
            except exc.NoResultFound, e: 
                return "request token: %s not found" %request_key
        else:
            return web.internalerror()
        client = OAuthClient(key=API_KEY, secret=SECRET)
        access_key, access_secret = client.get_access_token(request_key, token.secret)
        if not access_key or not access_secret:
            return "Error: access_key: %s access_token: %s" %(access_key, access_secret)
        
	    print "access_key %s, access_secret %s" %(access_key, access_secret)
        service = DoubanService(api_key=API_KEY, secret=SECRET)
        
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


        # check if the user has bind another jid
        #try:
        #    user = session.query(User).filter_by(uid=people.uid.text).one()
        #    if user.jid != authen.jid:
        #        return "Faile: the user has already associated with a jid: %s" %user.jid
        #except:
        #    pass
         
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
        return "OK, authenication of user: %s, jid: %s finished, enjoy it!" %(user.uid, user.jid)
        

class subscribe:
    def GET(self, jid):
        return 'you cannot use this'
        session = Session()
        hash = Authen.get_authen_code(jid, session)
        if hash is False:
            hash = Authen.gen_authen_code(jid, session)
        if hash is False:
            return "fail %s" %hash
        raise web.seeother("/douban/auth/%s" %hash)

application = web.application(urls, globals(), web.reloader).wsgifunc()
#app.run()


