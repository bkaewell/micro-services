import time
import pathlib
import gspread

from .config import Config
from gspread import authorize
from .logger import get_logger


logger = get_logger("google_sheets")

# Cache Setup 
if pathlib.Path("/.dockerenv").exists():
    cache_dir = pathlib.Path("/data/cache")
else:
    cache_dir = pathlib.Path.home() / ".cache" / "update_dns"

cache_dir.mkdir(parents=True, exist_ok=True)
id_cache_file = cache_dir / 'google_sheet_id.txt'


def get_gspread_client(self) -> gspread.Client:
    """Returns the cached client, re-authenticating only if the TTL has expired"""
    
    current_time = time.time()


def get_worksheet(self, gc: gspread.Client) -> gspread.Worksheet:
    """Resolves and caches the Spreadsheet ID, then returns the worksheet object."""
    

def upload_ip(self):
    """ <DOCSTRINGS> """
    gc = get_gspread_client(self)
    ws = get_worksheet(self, gc)
