import sys
sys.path.append('lib')

import models
from sqlalchemy import *

#models._metadata.drop_all(models._engine)
models._metadata.create_all(models._engine)
