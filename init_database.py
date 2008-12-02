import sys
sys.path.append('lib')

import models
from sqlalchemy import *

col = Column('active_even_offline', Boolean, default=False);
col.create(models._users_table)

#models._metadata.drop_all(models._engine)
#models._metadata.create_all(models._engine)
