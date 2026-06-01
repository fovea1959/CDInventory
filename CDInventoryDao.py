import logging
import os
import sys

from sqlalchemy.orm import Session
from sqlalchemy import select, create_engine
from sqlalchemy.engine.result import ScalarResult

import CDInventoryEntities

logger = logging.getLogger("dao")

defaultFilename = "CDInventory.db"


def engine(filename: str = None, echo: bool = False):
    if filename is None:
        filename = defaultFilename
    return create_engine(f'sqlite:///{filename}', echo=echo)


def main(argv):
    try:
        os.remove(defaultFilename)
    except FileNotFoundError:
        pass
    CDInventoryEntities.Base.metadata.create_all(engine())


if __name__ == '__main__':
    main(sys.argv[1:])