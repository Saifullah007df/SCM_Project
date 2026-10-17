import hashlib
import json
import math
import os
import tempfile
from pathlib import Path


FIELDS = {'schema_version', 'profile_id', 'demo_heart_rate_upper_bpm', 'demo_spo2_lower_percent', 'alarm_enabled'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(raw):
    obj = json.loads(raw)
    if not isinstance(obj, dict) or set(obj) != FIELDS:
        raise ValueError('Configuration keys do not match the demo schema')
    if type(obj['schema_version']) is not int or obj['schema_version'] != 1:
        raise ValueError('Unsupported schema')
    if obj['profile_id'] not in {'demo-adult', 'demo-legacy'}:
        raise ValueError('Unknown demonstration profile')
    if type(obj['alarm_enabled']) is not bool:
        raise ValueError('alarm_enabled must be boolean')
    for field in ['demo_heart_rate_upper_bpm', 'demo_spo2_lower_percent']:
        value = obj[field]
        if type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 300:
            raise ValueError('Invalid synthetic numeric fixture')
    return obj


def encode(obj):
    return (json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def atomic_write(path, raw):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Refusing symlink target')
    fd, temporary = tempfile.mkstemp(prefix='.aegis-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def stable_read(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as handle:
        first = os.fstat(handle.fileno())
        if first.st_size > 65536:
            raise ValueError('Configuration exceeds 64 KiB')
        raw = handle.read(65537)
        second = os.fstat(handle.fileno())
        if (first.st_ino, first.st_mtime_ns, first.st_size) != (second.st_ino, second.st_mtime_ns, second.st_size):
            raise ValueError('File changed during inspection')
        return raw
