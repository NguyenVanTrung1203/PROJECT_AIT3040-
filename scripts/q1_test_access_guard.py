"""Q1 pytest read guard for the locked Test split; hashing only."""
import os
from pathlib import Path
import inspect
import numpy as np
import pandas as pd
root=(Path(os.environ['DATASET_ROOT']).resolve()/'test').resolve()
counters={'hash_opens':0,'blocked_deserialization':0,'blocked_other_opens':0}
original_open=Path.open
original_np_load=np.load
original_parquet=pd.read_parquet
original_csv=pd.read_csv

def is_test_path(value):
    if not isinstance(value,(str,os.PathLike)):return False
    try:return Path(value).resolve().is_relative_to(root)
    except (OSError,ValueError):return False

def guarded_open(path,*args,**kwargs):
    if is_test_path(path):
        allowed=any(f.function=='checksum_dataset' and f.filename.replace('\\','/').endswith('/src/data/tensor_verification.py') for f in inspect.stack())
        if not allowed:
            counters['blocked_other_opens']+=1
            raise RuntimeError('Q1 prohibits Test content access outside checksum')
        counters['hash_opens']+=1
    return original_open(path,*args,**kwargs)

def checked(original):
    def wrapper(value,*args,**kwargs):
        if is_test_path(value):
            counters['blocked_deserialization']+=1
            raise RuntimeError('Q1 prohibits Test content deserialization')
        return original(value,*args,**kwargs)
    return wrapper

def pytest_sessionstart(session):
    Path.open=guarded_open
    np.load=checked(original_np_load)
    pd.read_parquet=checked(original_parquet)
    pd.read_csv=checked(original_csv)

def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line('Q1_ACCESS_GUARD: '+repr(counters))
