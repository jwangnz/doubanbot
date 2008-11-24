import sys
sys.path.append('lib')

import models

#models._metadata.drop_all(models._engine)
models._metadata.create_all(models._engine)
