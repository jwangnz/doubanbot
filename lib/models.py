from __future__ import with_statement
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker, mapper, relation, backref, exc
import hashlib, time, random, datetime

from doubanbot import config

_engine = create_engine(config.DATABASE, echo=False)
_metadata = MetaData()

Session = sessionmaker()

# Adding methods to Session so it can work with a with statement
def _session_enter(self):
    return self
 
def _session_exit(self, *exc):
    self.close()
 
Session.__enter__ = _session_enter
Session.__exit__ = _session_exit
Session.configure(bind=_engine)

def wants_session(orig):
    def f(*args):
        with Session() as session:
            return orig(*args + (session,))
    return f

class User(object):

    def is_quiet(self):
        if self.quiet_until: 
            return self.quiet_until > datetime.datetime.now()
        return False

    @staticmethod
    def by_jid(jid, session=None):
        s=session
        if not s:
            s=Session()
        try:
            return s.query(User).filter_by(jid=jid).one()
        finally:
            if not session:
                s.close()

    @staticmethod
    def update_status(jid, status, session=None):
        """Find or create a user by jid and set the user's status"""
        s = session
        if not s:
            s = Session()
        if not status:
            status = 'online'
        try:
            u = User.by_jid(jid, s)
        except:
            u = User()
            u.id = jid
            u.jid = jid
            u.auth = False
        
        u.status = status        
        try:
            s.add(u)
            s.commit()
            return u
        finally:
            if not session:
                s.close()

    @staticmethod
    def to_check(session, timeout=1):
        query = """select * from users
                    where users.active = :uactive 
                    and users.auth = :uauth
                    and users.status not in ('dnd', 'offline', 'unavailable', 'unsubscribed')
                    and (users.last_check is null or users.last_check < :ulast_check)
                    limit 50
                """
        then = datetime.datetime.now() - datetime.timedelta(minutes=timeout)
        return session.query(User).from_statement(query).params(
            uactive=True, uauth=True, ulast_check=then)
        

class Authen(object):
    def __init__(self, jid, hash):
        self.jid = jid
        self.hash = hash

    @staticmethod
    def get_authen_code(jid, session=None):
        s = session
        if not s:
	        s = Session()
        try:
            data = s.query(Authen).filter_by(jid=jid).one()
            timeout_date = datetime.datetime.now() - datetime.timedelta(minutes=int(config.AUTH_TIMEOUT))
            if data.last_modified and data.last_modified > timeout_date:
                return data.hash
        except exc.NoResultFound, e:
            pass
        finally:
            if not session:
                s.close()
        return False

    @staticmethod
    def gen_authen_code(jid, session=None):
        hash = Authen.get_authen_code(jid, session)
        if hash is not False:
            return hash

        s = session
        if not s:
           s = Session()
        secs = time.time()
        rand = random.random()
        hash = hashlib.md5("%s %d %f" %(jid, secs, rand)).hexdigest()
        try:
            record = s.query(Authen).filter_by(jid=jid).one()
            record.hash = hash
            record.jid = jid
        except:
            record = Authen(jid, hash)

        try:
            s.add(record)
            s.commit()
            return hash
        except:
            pass
        finally:
            if not session:
                s.close()
        return False 

class Token(object):
    def __init__(self, key, secret, hash):
        self.key = key
        self.secret = secret
        self.hash = hash
 

_users_table = Table('users', _metadata,
    Column('jid', String(128), primary_key=True, index=True, unique=True),
    Column('uid', String(128), index=True),
    Column('key', String(32)),
    Column('secret', String(16)),
    Column('name', String(255)),
    Column('active', Boolean, default=True),
    Column('auth', Boolean, default=False),
    Column('status', String(50)),
    Column('language', String(2)),
    Column('auto_post', Boolean, default=False),
    Column('quiet_until', DateTime),
    Column('create_date', DateTime, default=datetime.datetime.now),
    Column('last_check', DateTime),
    Column('last_cb_id', Integer),
    Column('last_dm_id', Integer),
    Column('last_modified', DateTime, onupdate=datetime.datetime.now),
)

_authen_table = Table('authen', _metadata,
    Column('hash', String(32), primary_key=True, index=True, unique=True),
    Column('jid', String(128), index=True, unique=True),
    Column('last_modified', DateTime, onupdate=datetime.datetime.now),
)

_tokens_table = Table('tokens', _metadata,
   Column('key', String(32), primary_key=True, index=True, unique=True),
   Column('secret', String(16), index=True, unique=True),
   Column('hash', String(32)),
   Column('last_modified', DateTime, onupdate=datetime.datetime.now),
)


mapper(User, _users_table)
mapper(Authen, _authen_table)
mapper(Token, _tokens_table)
