import logging
import os
import sys
from contextlib import suppress

from dotenv import load_dotenv

if 'DYNO' not in os.environ:
    with suppress(Exception):
        load_dotenv()

VALID_CONFIG = os.environ.get('ENV_VALID')
if not VALID_CONFIG:
    print('NOT VALID ENVIRONMENT VARIABLES (see config.py file)')
    sys.exit(0)

TEST = os.environ.get('TEST')

BOT_API_KEY = os.environ.get('BOT_API_KEY')
BOT_ID = int(BOT_API_KEY.split(':')[0])
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')


CONTENT_ITEMS_LIMIT = os.environ.get('CONTENT_ITEMS_LIMIT', 5)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


PG_URL = os.environ.get('PG_URL')

