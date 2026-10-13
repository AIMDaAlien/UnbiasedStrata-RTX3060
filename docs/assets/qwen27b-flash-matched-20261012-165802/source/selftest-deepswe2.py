#!/usr/bin/env python3
"""Prove every deepswe2 task is SOUND before a single model call is spent on it.

For each task this checks three things:

  1. NEGATIVE  the shipped kit (the broken code) must FAIL its own check.
     If the broken code already passes, the task tests nothing.
  2. POSITIVE  a reference solution must PASS the check.
     If the reference fails, the task is impossible and every model will score 0
     for a reason that is the pack's fault, not the model's.
  3. GRADER    the extracted file blocks must be the ones the runner would accept,
     and a model that emits nothing must score `no-file-blocks`, not a pass.

Run from ~/bench:  python3 selftest-deepswe2.py
"""
import json
import os
import subprocess
import sys
import tempfile
import textwrap

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from bench_lib import extract_files  # noqa: E402

PACK = os.path.join(ROOT, "packs", "deepswe2", "pack.json")


def materialise(kit, tmp):
    for rel, content in kit.items():
        fp = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(fp) or tmp, exist_ok=True)
        with open(fp, "w") as f:
            f.write(content)


def run_check(kit, files, check, timeout=300):
    """Reproduce grade_files: materialise kit, overlay the model's files, run check."""
    tmp = tempfile.mkdtemp(prefix="dsw-selftest-")
    try:
        materialise(kit, tmp)
        for rel, content in (files or {}).items():
            fp = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(fp) or tmp, exist_ok=True)
            with open(fp, "w") as f:
                f.write(content)
        cp = os.path.join(tmp, "_check.py")
        with open(cp, "w") as f:
            f.write(check)
        try:
            c = subprocess.run([sys.executable, cp], capture_output=True,
                               text=True, timeout=timeout, cwd=tmp)
        except subprocess.TimeoutExpired:
            return None, "check-timeout"
        if c.returncode == 0:
            return True, "ok"
        err = (c.stderr or "").strip().splitlines()
        return False, (err[-1][:120] if err else f"exit {c.returncode}")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- references
# A correct implementation per task. Only the files that CHANGE are listed, which is
# exactly the contract the prompt states.
REF = {}

REF['e1-bounded-queue-close'] = {
    'wpool/queue.py': r'''
"""A bounded work queue."""
import threading
import time


class Full(Exception):
    pass


class Closed(Exception):
    pass


class Queue:
    def __init__(self, maxsize=0):
        self.maxsize = maxsize
        self._items = []
        self._closed = False
        self.unfinished = 0
        self._cv = threading.Condition(threading.RLock())

    def get(self, timeout=None):
        with self._cv:
            if self._items:
                self.unfinished += 1
                return self._items.pop(0)
            if self._closed:
                return None
            deadline = None if timeout is None else time.monotonic() + timeout
            while not self._items and not self._closed:
                if deadline is None:
                    self._cv.wait()
                else:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        return None
                    self._cv.wait(left)
            if self._items:
                self.unfinished += 1
                return self._items.pop(0)
            return None

    def put(self, item, timeout=None):
        with self._cv:
            if self._closed:
                raise Closed("queue is closed")
            if not self.maxsize:
                self._items.append(item)
                self._cv.notify()
                return True
            deadline = None if timeout is None else time.monotonic() + timeout
            while len(self._items) >= self.maxsize and not self._closed:
                if deadline is None:
                    self._cv.wait()
                else:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        raise Full("queue is full")
                    self._cv.wait(left)
            if self._closed:
                raise Closed("queue is closed")
            self._items.append(item)
            self._cv.notify()
            return True

    def task_done(self):
        with self._cv:
            self.unfinished -= 1
            if self.unfinished <= 0:
                self.unfinished = 0
                self._cv.notify_all()

    def close(self):
        with self._cv:
            self._closed = True
            self._cv.notify_all()

    def join(self, timeout=None):
        with self._cv:
            deadline = None if timeout is None else time.monotonic() + timeout
            while self.unfinished > 0:
                if deadline is None:
                    self._cv.wait()
                else:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        raise Full("work outstanding")
                    self._cv.wait(left)
''',
}

REF["e2-lru-eviction"] = {
    "cachebox/lru.py": '''
"""Least-recently-used cache."""


class LRU:
    def __init__(self, capacity):
        self.capacity = capacity
        self._data = {}
        self._order = []          # least-recently-used first

    def get(self, key):
        key = _k(key)
        if key not in self._data:
            return None
        self._order.remove(key)
        self._order.append(key)
        return self._data[key]

    def put(self, key, value):
        key = _k(key)
        if key in self._data:
            self._order.remove(key)
        self._order.append(key)
        self._data[key] = value
        if self.capacity and self.capacity > 0:
            while len(self._order) > self.capacity:
                old = self._order.pop(0)
                self._data.pop(old, None)

    def keys(self):
        return list(reversed(self._order))

    def delete(self, key):
        key = _k(key)
        if key in self._data:
            del self._data[key]
            self._order.remove(key)
            return True
        return False

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return _k(key) in self._data


def _k(key):
    return key if isinstance(key, str) else str(key)
''',
}

REF['e3-retry-idempotent'] = {
    'apiwrap/client.py': r'''
"""HTTP client with retries."""
import time

IDEMPOTENT = ('GET', 'HEAD', 'PUT', 'DELETE')


class Transient(Exception):
    pass


class Client:
    def __init__(self, transport, backoff=0.01):
        self.transport = transport
        self.backoff = backoff

    def call(self, method, path, body=None, timeout=1.0, attempts=3,
             idempotency_key=None):
        method = method.upper()
        retryable = (method in IDEMPOTENT
                     or (method == 'POST' and idempotency_key is not None))
        headers = {}
        if idempotency_key is not None:
            headers['Idempotency-Key'] = idempotency_key
        last = None
        for i in range(attempts):
            if i:
                time.sleep(self.backoff * 2 ** (i - 1))
            try:
                return self.transport(method, path, body, headers)
            except Transient as e:
                last = e
                if not retryable:
                    raise
        raise last
''',
}

REF['e4-session-store-split'] = {
    'sess/__init__.py': r'''
from .store import SessionStore
from .memory import MemoryStore
from .errors import SessionError, UnknownSession

__all__ = ["SessionStore", "MemoryStore", "SessionError", "UnknownSession"]
''',
    'sess/errors.py': r'''
"""Session errors."""


class SessionError(Exception):
    pass


class UnknownSession(SessionError):
    pass
''',
    'sess/memory.py': r'''
"""In-memory session backend."""
import time

from .errors import UnknownSession


class MemoryStore:
    """Owns the timestamps: ttl seconds after the last touch means gone."""

    def __init__(self, ttl=None, clock=None):
        self.ttl = ttl
        self._clock = clock or time.monotonic
        self._data = {}          # sid -> [value, touched_at]

    def _expired(self, touched_at):
        return self.ttl is not None and (self._clock() - touched_at) >= self.ttl

    def _live(self, sid):
        rec = self._data.get(sid)
        if rec is None:
            raise UnknownSession(sid)
        if self._expired(rec[1]):
            del self._data[sid]
            raise UnknownSession(sid)
        return rec

    def get(self, sid):
        return self._live(sid)[0]

    def set(self, sid, value, now=None, ttl=None):
        self._data[sid] = [value, self._clock() if now is None else now]

    def touch(self, sid, now=None):
        rec = self._live(sid)
        rec[1] = self._clock() if now is None else now

    def delete(self, sid):
        self._data.pop(sid, None)

    def clear(self):
        self._data.clear()

    def keys(self):
        out = []
        for sid, rec in self._data.items():
            if not self._expired(rec[1]):
                out.append(sid)
        out.sort(key=lambda s: (self._data[s][1], s))
        return out

    def purge(self):
        dead = [sid for sid, rec in self._data.items() if self._expired(rec[1])]
        for sid in dead:
            del self._data[sid]
        return dead
''',
    'sess/store.py': r'''
"""Session storage (thin wrapper over a backend)."""
import time

from .errors import SessionError, UnknownSession
from .memory import MemoryStore


class SessionStore:
    def __init__(self, ttl=3600, backend=None, clock=None):
        self.ttl = ttl
        self.clock = clock or time.monotonic
        self.backend = backend if backend is not None else MemoryStore(
            ttl=ttl, clock=self.clock)

    def get(self, sid):
        return self.backend.get(sid)

    def set(self, sid, value):
        return self.backend.set(sid, value)

    def delete(self, sid):
        return self.backend.delete(sid)

    def touch(self, sid):
        return self.backend.touch(sid)

    def clear(self):
        return self.backend.clear()

    def keys(self):
        return self.backend.keys()
''',
}

REF["e5-validate-pipeline"] = {
    "vp/errors.py": '''
"""Validation errors."""


class ValidationError(Exception):
    pass


class MissingField(ValidationError):
    pass


class BadType(ValidationError):
    pass


class BadValue(ValidationError):
    pass
''',
    "vp/validate.py": '''
"""Schema validation."""
from .errors import BadType, BadValue, MissingField

ORDER = {BadType: 0, BadValue: 1, MissingField: 2}


def _isinstance(value, want):
    if isinstance(want, tuple):
        return isinstance(value, want)
    return isinstance(value, want)


def validate(obj, schema):
    """Coerce obj against schema. Returns a NEW dict, never mutates obj."""
    if not isinstance(obj, dict):
        raise BadType(f"object must be a dict, got {type(obj).__name__}")
    problems = []
    out = {}
    for name, spec in schema.items():
        want = spec.get('type', str)
        present = name in obj
        value = obj.get(name)
        if not present or value is None:
            if spec.get('required'):
                problems.append((ORDER[MissingField], MissingField(f"missing field: {name}")))
            else:
                out[name] = spec.get('default')
            continue
        if not _isinstance(value, want):
            problems.append((ORDER[BadType], BadType(f"{name}: expected {want}, got {type(value).__name__}")))
            continue
        choices = spec.get('choices')
        if choices is not None and value not in choices:
            problems.append((ORDER[BadValue], BadValue(f"{name}: {value!r} not in {choices}")))
            continue
        out[name] = value
    if problems:
        problems.sort(key=lambda p: p[0])
        raise problems[0][1]
    return out
''',
    "vp/queue.py": '''
"""Request intake queue."""
from collections import deque

from .validate import validate


class RequestQueue:
    def __init__(self, schema):
        self.schema = schema
        self._items = deque()

    def submit(self, obj):
        coerced = validate(obj, self.schema)
        self._items.append(coerced)
        return coerced

    def pending(self):
        return len(self._items)

    def drain(self):
        out = list(self._items)
        self._items.clear()
        return out
''',
    "vp/__init__.py": '''
from .queue import RequestQueue
from .validate import validate
from .errors import ValidationError, MissingField, BadType, BadValue

__all__ = ["RequestQueue", "validate", "ValidationError", "MissingField",
           "BadType", "BadValue"]
''',
}

REF['e6-index-rebuild'] = {
    'tindex/builder.py': r'''
"""Index construction: incremental, bounded memory."""
import re

CHUNK = 64
WORD = re.compile(r"\S+")


def _chunk_entries(pairs):
    """Return [(term, doc_id, positions)] for one chunk of documents."""
    slots = {}
    for doc_id, text in pairs:
        for pos, word in enumerate(WORD.findall(text or "")):
            slots.setdefault((word, doc_id), []).append(pos)
    return [(word, doc_id, positions)
            for (word, doc_id), positions in slots.items()]


def build(pairs, chunk=CHUNK):
    """Yield one batch of postings entries per `chunk` documents, lazily."""
    if chunk <= 0:
        raise ValueError('chunk must be positive')
    batch = []
    seen = 0
    for pair in pairs:
        batch.append(pair)
        seen += 1
        if seen % chunk == 0:
            yield _chunk_entries(batch)
            batch = []
    if batch:
        yield _chunk_entries(batch)


def merge(base, extra):
    """Merge a batch of postings entries into `base` in place."""
    for term, doc_id, positions in extra:
        slot = base.setdefault(term, {}).setdefault(doc_id, [])
        base[term][doc_id] = sorted(set(slot) | set(positions))
    return base
''',
    'tindex/index.py': r'''
"""The index object."""
from . import builder


class Index:
    def __init__(self):
        self._idx = {}
        self._docs = 0

    def add(self, doc_id, text):
        for batch in builder.build([(doc_id, text)]):
            builder.merge(self._idx, batch)
        self._docs += 1

    def rebuild(self, pairs):
        pairs = list(pairs)
        fresh = {}
        for batch in builder.build(pairs):
            builder.merge(fresh, batch)
        self._idx = fresh
        self._docs = len({doc for doc, _text in pairs})
        return sum(len(p) for docs in self._idx.values() for p in docs.values())

    def lookup(self, term):
        return sorted(self._idx.get(term, {}).keys())

    def doc_count(self):
        return self._docs

    def terms(self):
        return sorted(self._idx.keys())
''',
}

REF['e7-money-rounding'] = {
    'ledger/money.py': r'''
"""Exact money arithmetic (integer cents, half-up rounding)."""
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal('1')


class CurrencyMismatch(Exception):
    pass


def _to_cents(amount):
    """Exact decimal amount -> integer cents, rounded HALF UP."""
    if isinstance(amount, Money):
        return amount.cents
    if isinstance(amount, int):
        return amount * 100
    return int((Decimal(str(amount)) * 100).quantize(CENT, rounding=ROUND_HALF_UP))


class Money:
    def __init__(self, amount=0, currency='USD'):
        self.currency = currency
        self.cents = _to_cents(amount)

    @classmethod
    def _from_cents(cls, cents, currency):
        out = cls.__new__(cls)
        out.currency = currency
        out.cents = int(cents)
        return out

    def _same(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        if other.currency != self.currency:
            raise CurrencyMismatch(f"{self.currency} vs {other.currency}")
        return other

    def __add__(self, other):
        other = self._same(other)
        if other is NotImplemented:
            return NotImplemented
        return Money._from_cents(self.cents + other.cents, self.currency)

    def __sub__(self, other):
        other = self._same(other)
        if other is NotImplemented:
            return NotImplemented
        return Money._from_cents(self.cents - other.cents, self.currency)

    def __mul__(self, k):
        if isinstance(k, Money):
            return NotImplemented
        cents = (Decimal(self.cents) * Decimal(str(k))).quantize(
            CENT, rounding=ROUND_HALF_UP)
        return Money._from_cents(cents, self.currency)

    __rmul__ = __mul__

    def __neg__(self):
        return Money._from_cents(-self.cents, self.currency)

    def __eq__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        return (self.cents, self.currency) == (other.cents, other.currency)

    def __lt__(self, other):
        other = self._same(other)
        if other is NotImplemented:
            return NotImplemented
        return self.cents < other.cents

    def __hash__(self):
        return hash((self.cents, self.currency))

    def allocate(self, pairs):
        pairs = list(pairs)
        for key, weight in pairs:
            if not isinstance(weight, (int, float)) or weight <= 0:
                raise ValueError(f"weight for {key!r} must be positive, got {weight!r}")
        out = {key: Money._from_cents(0, self.currency) for key, _w in pairs}
        if not pairs or self.cents == 0:
            return out
        total = sum(w for _k, w in pairs)
        cents = {key: (self.cents * w) // total for key, w in pairs}
        left = self.cents - sum(cents.values())
        order = sorted(range(len(pairs)), key=lambda i: (-pairs[i][1], i))
        i = 0
        while left > 0:
            key = pairs[order[i % len(order)]][0]
            cents[key] += 1
            left -= 1
            i += 1
        return {key: Money._from_cents(cents[key], self.currency) for key in cents}

    def format(self):
        sign = '-' if self.cents < 0 else ''
        c = abs(self.cents)
        sym = {'USD': '$', 'EUR': '\u20ac', 'GBP': '\u00a3'}.get(
            self.currency, self.currency + ' ')
        return f"{sign}{sym}{c // 100}.{c % 100:02d}"
''',
}

REF['e8-event-sourcing'] = {
    'evt/aggregate.py': r'''
"""Event-sourced aggregate."""
import copy


class InvalidEvent(Exception):
    pass


class Aggregate:
    def __init__(self):
        self.state = {'count': 0, 'total': 0}
        self.version = 0
        self.pending = []
        self._seqs = set()

    def handle(self, command):
        """Decide only: return new events, record them as pending, mutate nothing."""
        events = [{'name': 'added', 'amount': command.get('amount', 0)}]
        self.pending.extend(events)
        return events

    def apply(self, event):
        """Validate against current state; on a failed guard change NOTHING."""
        name = event.get('name')
        if name != 'added':
            raise InvalidEvent(f"unknown event: {name!r}")
        seq = event.get('seq')
        if seq is not None and seq in self._seqs:
            raise InvalidEvent(f"duplicate seq: {seq}")
        new = dict(self.state)
        new['count'] += 1
        new['total'] += event.get('amount', 0)
        if new['total'] < 0:
            raise InvalidEvent('total would go negative')
        self.state = new
        if seq is not None:
            self._seqs.add(seq)
        self.version += 1
        if event in self.pending:
            self.pending.remove(event)
        return self.state

    def rehydrate(self, events):
        for e in events:
            self.apply(e)
        return self

    def snapshot(self):
        return copy.deepcopy(self.state)
''',
}

REF['e9-parallel-dedup'] = {
    'pdedup/store.py': r'''
"""Deduplicating store: atomic put_if_absent, chunked processing."""
import itertools
import threading


class Store:
    def __init__(self):
        self._data = {}
        self._offered = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            return self._data.get(key)

    def put_if_absent(self, key, value):
        """Atomic check-then-set: exactly one caller wins a given key."""
        with self._lock:
            self._offered[key] = self._offered.get(key, 0) + 1
            if key in self._data:
                return False
            self._data[key] = value
            return True

    def process(self, items, chunk=500):
        """Store each pair, consuming the iterable one chunk at a time."""
        if chunk <= 0:
            raise ValueError('chunk must be positive')
        stored = dupes = 0
        it = iter(items)
        while True:
            buf = list(itertools.islice(it, chunk))
            if not buf:
                break
            for key, value in buf:
                if self.put_if_absent(key, value):
                    stored += 1
                else:
                    dupes += 1
        return {'stored': stored, 'duplicates': dupes}

    def stats(self):
        with self._lock:
            return {'keys': len(self._data),
                    'contended': sum(1 for n in self._offered.values() if n > 1)}

    def __len__(self):
        with self._lock:
            return len(self._data)
''',
}

REF['e10-csv-dialect'] = {
    'imp/csvimport.py': r'''
"""CSV reading and writing across dialects."""
import csv as _csv
import io
import os

DIALECTS = {'excel': ',', 'excel-tab': '\t', 'pipe': '|'}


def _delim(dialect, delimiter):
    if delimiter is not None:
        return delimiter
    return DIALECTS.get(dialect, ',')


class Reader:
    def __init__(self, source, dialect='excel', delimiter=None):
        if hasattr(source, 'read'):
            self._text = source.read()
        else:
            self._text = source if source is not None else ''
        self.dialect = dialect
        self.delimiter = _delim(dialect, delimiter)
        self._rows = list(_csv.reader(io.StringIO(self._text),
                                      delimiter=self.delimiter))

    @classmethod
    def read(cls, path_or_text):
        """An existing path is opened; anything else is treated as CSV text."""
        if isinstance(path_or_text, str) and os.path.exists(path_or_text):
            with open(path_or_text, newline='') as f:
                return cls(f.read())
        return cls(path_or_text)

    @property
    def fieldnames(self):
        if not self._rows:
            return []
        return [h.strip() for h in self._rows[0]]

    def rows(self):
        names = self.fieldnames
        for raw in self._rows[1:]:
            if not any(c.strip() for c in raw):
                continue
            yield {names[i]: (raw[i].strip() if i < len(raw) else None)
                   for i in range(len(names))}

    @staticmethod
    def write(path, fieldnames, rows, dialect='excel'):
        d = _delim(dialect, None)
        with open(path, 'w', newline='') as f:
            w = _csv.writer(f, delimiter=d, lineterminator='\n',
                            quoting=_csv.QUOTE_MINIMAL)
            w.writerow(list(fieldnames))
            for r in rows:
                w.writerow([r.get(n) for n in fieldnames])
''',
}

REF['e11-scheduler-priority'] = {
    'sched/runner.py': r'''
"""Fair job runner: priority + per-tenant fairness + error isolation."""
import itertools


class _Job:
    __slots__ = ('tenant', 'fn', 'priority', 'seq')

    def __init__(self, tenant, fn, priority, seq):
        self.tenant = tenant
        self.fn = fn
        self.priority = priority
        self.seq = seq

    @property
    def key(self):
        return (-self.priority, self.seq)


class Runner:
    def __init__(self, max_per_tenant=2):
        self.max_per_tenant = max_per_tenant
        self._q = []
        self._seq = itertools.count()
        self._results = []
        self._failed = 0
        self._streak_tenant = None
        self._streak = 0

    def submit(self, tenant, fn, priority=0):
        self._q.append(_Job(tenant, fn, priority, next(self._seq)))

    def _pick(self):
        if not self._q:
            return None
        blocked = (self._streak_tenant is not None
                   and self._streak >= self.max_per_tenant)
        eligible = [j for j in self._q
                    if not (blocked and j.tenant == self._streak_tenant)]
        pool = eligible or self._q
        return min(pool, key=lambda j: j.key)

    def run(self, limit=None):
        ran = 0
        while limit is None or ran < limit:
            job = self._pick()
            if job is None:
                break
            self._q.remove(job)
            if self._streak_tenant == job.tenant:
                self._streak += 1
            else:
                self._streak_tenant = job.tenant
                self._streak = 1
            ran += 1
            try:
                out = job.fn()
            except Exception as e:
                self._failed += 1
                self._results.append({'ok': False, 'error': str(e)})
            else:
                self._results.append(out)
        return self._results[-ran:] if ran else []

    def pending(self):
        return len(self._q)

    def stats(self):
        return {'run': len(self._results),
                'failed': self._failed,
                'skipped': len(self._q)}

    def reset(self):
        self._q = []
        self._streak_tenant = None
        self._streak = 0
''',
}

REF['e12-schema-migration'] = {
    'mig/__init__.py': r'''
from .runner import plan, migrate, applied, rollback_last
from .errors import MigrationError

__all__ = ["plan", "migrate", "applied", "rollback_last", "MigrationError"]
''',
    'mig/runner.py': r'''
"""Migration runner: dependency-ordered, with rollback."""
from .errors import MigrationError


def plan(migrations):
    """Names in dependency order; independent names break ties alphabetically."""
    by_name = {}
    for m in migrations:
        if m['name'] in by_name:
            raise MigrationError(f"duplicate migration name: {m['name']}")
        by_name[m['name']] = m
    for m in migrations:
        for d in m.get('deps', ()):
            if d not in by_name:
                raise MigrationError(f"{m['name']} depends on unknown {d}")
    ordered = []
    placed = set()
    remaining = sorted(by_name)
    while remaining:
        ready = [n for n in remaining
                 if all(d in placed for d in by_name[n].get('deps', ()))]
        if not ready:
            raise MigrationError('dependency cycle among ' + ','.join(remaining))
        n = ready[0]
        ordered.append(n)
        placed.add(n)
        remaining.remove(n)
    return ordered


def applied(db):
    return set(db.applied_migrations)


def migrate(conn, migrations, db, dry_run=False):
    by_name = {m['name']: m for m in migrations}
    todo = [n for n in plan(migrations) if n not in applied(db)]
    if dry_run:
        return todo
    did = []
    try:
        for name in todo:
            by_name[name]['up'](conn)
            db.record(name)
            did.append(name)
    except Exception:
        for name in reversed(did):
            by_name[name]['down'](conn)
            if name in db.applied_migrations:
                db.applied_migrations.remove(name)
        raise
    return did


def rollback_last(conn, migrations, db):
    if not db.applied_migrations:
        return None
    name = db.applied_migrations[-1]
    by_name = {m['name']: m for m in migrations}
    if name in by_name:
        by_name[name]['down'](conn)
    db.applied_migrations.remove(name)
    return name
''',
}

REF['e13-stream-window'] = {
    'swin/window.py': r'''
"""Non-overlapping windows with bounded memory."""
from collections import defaultdict, deque


class Windowed:
    _peak = 0

    def __init__(self, source, size, fn, key=None):
        if size <= 0:
            raise ValueError('size must be positive')
        self.source = source
        self.size = size
        self.fn = fn
        self.key = key

    @classmethod
    def _note(cls, held):
        if held > cls._peak:
            cls._peak = held

    @classmethod
    def peak_memory(cls):
        return cls._peak

    def __iter__(self):
        bufs = defaultdict(lambda: deque(maxlen=self.size))
        for item in self.source:
            k, v = item
            if self.key is not None:
                k = self.key(item)
            buf = bufs[k]
            buf.append(v)
            Windowed._note(len(buf))
            if len(buf) == self.size:
                yield (k, self.fn(list(buf)))
                bufs[k] = deque(maxlen=self.size)


def summarise(source, size, fn, key=None):
    return list(Windowed(source, size, fn, key))
''',
}

REF['e14-parser-precedence'] = {
    'expr/__init__.py': r'''
from .parser import parse, tokenize, ExprError
from .eval_unsafe import eval_unsafe

__all__ = ["parse", "tokenize", "ExprError", "eval_unsafe"]
''',
    'expr/parser.py': r'''
"""Infix expression parser with correct precedence."""
import re

TOKEN = re.compile(r"(?:(?P<num>\d+(?:\.\d+)?)|(?P<op>\*\*|//|[+\-*/%()<>]))")


class ExprError(Exception):
    pass


def tokenize(text):
    """Split `text` into numbers and operator/paren strings."""
    if not isinstance(text, str):
        raise ExprError('expression must be a string')
    out = []
    pos = 0
    while pos < len(text):
        if text[pos].isspace():
            pos += 1
            continue
        m = TOKEN.match(text, pos)
        if not m:
            raise ExprError(f'unexpected character at {pos}: {text[pos]!r}')
        if m.group('num') is not None:
            v = m.group('num')
            out.append(float(v) if '.' in v else int(v))
        else:
            out.append(m.group('op'))
        pos = m.end()
    if not out:
        raise ExprError('empty expression')
    return out


def _apply(op, a, b):
    if op == '+':
        return a + b
    if op == '-':
        return a - b
    if op == '*':
        return a * b
    if op == '/':
        if b == 0:
            raise ExprError('division by zero')
        return a / b
    if op == '//':
        if b == 0:
            raise ExprError('division by zero')
        return a // b
    if op == '%':
        if b == 0:
            raise ExprError('modulo by zero')
        return a % b
    if op == '**':
        return a ** b
    raise ExprError(f'unknown operator {op!r}')


def _atom(toks, i):
    """A primary: number, parenthesised expression, or unary +/-."""
    if i >= len(toks):
        raise ExprError('unexpected end of expression')
    t = toks[i]
    if t == '(':
        val, i = _expr(toks, i + 1)
        if i >= len(toks) or toks[i] != ')':
            raise ExprError('unbalanced parentheses')
        return val, i + 1
    if t in ('-', '+'):
        # the operand is a full power expression, so -2 ** 2 == -(2 ** 2)
        val, i = _power(toks, i + 1)
        return (-val if t == '-' else val), i
    if isinstance(t, (int, float)) and not isinstance(t, bool):
        return t, i + 1
    raise ExprError(f'unexpected token {t!r}')


def _power(toks, i):
    """`**` is right-associative; its left operand is a bare atom."""
    base, i = _atom(toks, i)
    if i < len(toks) and toks[i] == '**':
        exp, i = _power(toks, i + 1)
        try:
            return base ** exp, i
        except (ZeroDivisionError, OverflowError) as e:
            raise ExprError(str(e)) from e
    return base, i


def _term(toks, i):
    val, i = _power(toks, i)
    while i < len(toks) and toks[i] in ('*', '/', '//', '%'):
        op = toks[i]
        rhs, i = _power(toks, i + 1)
        val = _apply(op, val, rhs)
    return val, i


def _expr(toks, i):
    val, i = _term(toks, i)
    while i < len(toks) and toks[i] in ('+', '-'):
        op = toks[i]
        rhs, i = _term(toks, i + 1)
        val = _apply(op, val, rhs)
    return val, i


def parse(text):
    toks = tokenize(text)
    val, i = _expr(toks, 0)
    if i != len(toks):
        raise ExprError(f'trailing junk at token {i}: {toks[i]!r}')
    return val
''',
}

REF['e15-backpressure-queue'] = {
    'bpq/queue.py': r'''
"""Bounded queue with real backpressure."""
import threading
import time
from collections import deque


class Full(Exception):
    pass


class Closed(Exception):
    pass


class BoundedQueue:
    def __init__(self, maxsize=0):
        self.maxsize = maxsize if maxsize and maxsize > 0 else 0
        self._items = deque()
        self._closed = False
        self._cv = threading.Condition(threading.RLock())

    def put(self, item, timeout=None):
        with self._cv:
            if self._closed:
                return False
            if not self.maxsize:
                self._items.append(item)
                self._cv.notify()
                return True
            deadline = None if timeout is None else time.monotonic() + timeout
            while len(self._items) >= self.maxsize and not self._closed:
                if deadline is None:
                    self._cv.wait()
                else:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        raise Full("queue is full")
                    self._cv.wait(left)
            if self._closed:
                return False
            self._items.append(item)
            self._cv.notify()
            return True

    def get(self, timeout=None):
        with self._cv:
            if self._items:
                # notify a producer blocked on a full queue that there is room
                item = self._items.popleft()
                self._cv.notify()
                return item
            if self._closed:
                return None
            deadline = None if timeout is None else time.monotonic() + timeout
            while not self._items and not self._closed:
                if deadline is None:
                    self._cv.wait()
                else:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        return None
                    self._cv.wait(left)
            if self._items:
                item = self._items.popleft()
                self._cv.notify()
                return item
            return None

    def close(self):
        with self._cv:
            self._closed = True
            self._cv.notify_all()

    def qsize(self):
        with self._cv:
            return len(self._items)

    def drop_oldest(self):
        with self._cv:
            item = self._items.popleft() if self._items else None
            if item is not None:
                self._cv.notify()
            return item

    def __len__(self):
        return self.qsize()
''',
}

REF['e16-trie-autocomplete'] = {
    'ac/trie.py': r'''
"""Autocomplete trie."""


class _Node:
    __slots__ = ('children', 'weight', 'word')

    def __init__(self):
        self.children = {}
        self.weight = None
        self.word = None


class Trie:
    def __init__(self):
        self._root = _Node()
        self._words = {}

    def _find(self, word, create=False):
        node = self._root
        for ch in word:
            nxt = node.children.get(ch)
            if nxt is None:
                if not create:
                    return None
                nxt = _Node()
                node.children[ch] = nxt
            node = nxt
        return node

    def insert(self, word, weight=1):
        """Insert or REPLACE: inserting an existing word resets its weight."""
        word = _norm(word)
        if not word:
            return
        node = self._find(word, create=True)
        node.word = word
        node.weight = weight
        self._words[word] = weight

    def remove(self, word):
        word = _norm(word)
        if word in self._words:
            del self._words[word]
            node = self._find(word)
            if node is not None:
                node.word = None
                node.weight = None

    def update_weight(self, word, delta):
        """Adjust a weight, adding the word at `delta` when it is absent."""
        word = _norm(word)
        weight = self._words.get(word, 0) + delta
        self._words[word] = weight
        node = self._find(word, create=True)
        node.word = word
        node.weight = weight

    def complete(self, prefix, limit=10):
        """True-prefix matches, ordered by DESCENDING weight then A-Z."""
        prefix = _norm(prefix)
        node = self._root if not prefix else self._find(prefix)
        if node is None:
            return []
        hits = []
        stack = [(prefix, node)]
        while stack:
            pfx, n = stack.pop()
            if n.word is not None:
                hits.append((n.weight, pfx))
            for ch, child in n.children.items():
                stack.append((pfx + ch, child))
        hits.sort(key=lambda t: (-t[0], t[1]))
        if limit:
            return [w for _, w in hits[:limit]]
        return [w for _, w in hits]

    def longest_prefix_of(self, text):
        text = _norm(text)
        best = None
        node = self._root
        for i, ch in enumerate(text):
            node = node.children.get(ch)
            if node is None:
                break
            if node.word is not None:
                best = text[:i + 1]
        return best

    def words(self):
        return sorted(self._words)

    def __contains__(self, word):
        return _norm(word) in self._words

    def __len__(self):
        return len(self._words)


def _norm(w):
    return w.strip().lower() if isinstance(w, str) else str(w).lower()
''',
}

REF['e17-batch-chunking'] = {
    'batch/runner.py': r'''
"""Batch runner: lazy chunking + error isolation."""
from dataclasses import dataclass


@dataclass
class BatchStats:
    processed: int = 0
    failed: int = 0


def chunked(source, size):
    """Yield lists of at most `size` items, pulling from `source` lazily."""
    if size <= 0:
        raise ValueError('size must be positive')
    buf = []
    for item in source:
        buf.append(item)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


def run_batches(source, fn, size, on_error=None):
    """Apply `fn` to every chunk; a raising chunk yields None and is counted."""
    stats = BatchStats()
    results = []
    for buf in chunked(source, size):
        try:
            results.append(fn(buf))
            stats.processed += 1
        except Exception as exc:
            results.append(None)
            stats.failed += 1
            if on_error is not None:
                on_error(buf, exc)
    return results, stats
''',
}

REF['e18-ttl-cache'] = {
    'ttlcache/cache.py': r'''
"""Expiring cache."""
import time


class Cache:
    def __init__(self, default_ttl=None, get_clock=None):
        self.default_ttl = default_ttl
        self._clock = get_clock or time.monotonic
        self._data = {}          # key -> (value, expires_at or None)

    def _expiry(self, ttl):
        return None if ttl is None else self._clock() + ttl

    def _live(self, key):
        """Return (value, expires) if the key is present and unexpired."""
        rec = self._data.get(key)
        if rec is None:
            return None
        value, expires = rec
        if expires is not None and self._clock() >= expires:
            del self._data[key]
            return None
        return rec

    def put(self, key, value, ttl=None):
        if ttl is None:
            ttl = self.default_ttl
        self._data[key] = (value, self._expiry(ttl))

    def get(self, key):
        rec = self._live(key)
        return None if rec is None else rec[0]

    def get_or_set(self, key, factory, ttl=None):
        hit = self.get(key)
        if hit is not None:
            return hit
        value = factory()
        self.put(key, value, ttl)
        return value

    def delete(self, key):
        return self._data.pop(key, None) is not None

    def purge(self):
        """Drop every expired entry; return how many this call removed."""
        dead = [k for k, rec in list(self._data.items())
                if rec[1] is not None and self._clock() >= rec[1]]
        for k in dead:
            del self._data[k]
        return len(dead)

    def keys(self):
        return sorted(k for k in list(self._data) if self._live(k) is not None)

    def __len__(self):
        return len(self.keys())

    def __contains__(self, key):
        return self._live(key) is not None
''',
}

REF["e19-idempotent-http"] = {
    "webhook/processor.py": '''
"""Idempotent webhook processing."""
import threading


class Processor:
    def __init__(self):
        self._lock = threading.Lock()
        self._done = {}
        self._inflight = set()

    def process(self, event_id, handler):
        with self._lock:
            if event_id in self._done:
                return {'ok': True, 'duplicate': True}
            if event_id in self._inflight:
                return {'ok': True, 'duplicate': True}
            self._inflight.add(event_id)
        try:
            value = handler(event_id)
        except BaseException:
            with self._lock:
                self._inflight.discard(event_id)
            raise
        with self._lock:
            self._inflight.discard(event_id)
            if not value:
                return {'ok': False, 'duplicate': False}
            self._done[event_id] = value
        return {'ok': True, 'duplicate': False}

    def result(self, event_id):
        return self._done.get(event_id)

    def seen(self, event_id):
        return event_id in self._done

    def forget(self, event_id):
        return self._done.pop(event_id, None) is not None

    def processed_count(self):
        return len(self._done)

    def clear(self):
        self._done.clear()
''',
}

REF['e20-iter-drain'] = {
    'drain/pipeline.py': r'''
"""Resource-safe draining."""


class DrainError(Exception):
    def __init__(self, message, items=None, cause=None):
        super().__init__(message)
        self.items = list(items or [])
        self.cause = cause


def _pull(source, n):
    if hasattr(source, 'read_batch'):
        return list(source.read_batch(n))
    return list(source)


def collect(source, batch_size=100):
    out = []
    try:
        while True:
            batch = _pull(source, batch_size)
            if not batch:
                break
            out.extend(batch)
    except Exception as e:
        raise DrainError(f'collect failed: {e}', items=out, cause=e) from e
    finally:
        source.close()
    return out


def drain(source):
    """Yield items one at a time, closing the source when done or abandoned."""
    try:
        while True:
            batch = _pull(source, 100)
            if not batch:
                return
            for item in batch:
                yield item
    finally:
        source.close()


def close_all(sources):
    failures = []
    for s in sources:
        try:
            s.close()
        except Exception as e:
            failures.append(f'{type(s).__name__}: {e}')
    if failures:
        raise DrainError('close failures: ' + '; '.join(failures))
    return None
''',
}

REF['e21-index-invalidation'] = {
    'depgraph/graph.py': r'''
"""Dependency graph with transitive invalidation."""
import json


class Graph:
    def __init__(self):
        self._mods = {}          # name -> {'provides': set, 'requires': set}

    def add_module(self, name, provides=(), requires=()):
        self._mods[name] = {'provides': set(provides), 'requires': set(requires)}

    def dependents(self, name):
        """Modules whose `requires` DIRECTLY include `name`, sorted."""
        return sorted(m for m, spec in self._mods.items()
                      if name in spec['requires'])

    def _seeds(self, name):
        """The starting module(s): `name` itself and whoever provides it."""
        seeds = set()
        if name in self._mods:
            seeds.add(name)
        for m, spec in self._mods.items():
            if name in spec['provides']:
                seeds.add(m)
        return seeds

    def _importers_of(self, module):
        """Modules that depend on `module`, by name or by a symbol it provides."""
        out = set()
        provides = self._mods[module]['provides']
        for m, spec in self._mods.items():
            if m == module:
                continue
            if module in spec['requires'] or (spec['requires'] & provides):
                out.add(m)
        return out

    def reverse_closure(self, name):
        """Everything reachable backwards from `name`: itself plus its importers."""
        seeds = self._seeds(name)
        out = set(seeds)
        frontier = list(seeds)
        while frontier:
            cur = frontier.pop()
            for dep in self._importers_of(cur):
                if dep not in out:
                    out.add(dep)
                    frontier.append(dep)
        return out

    def invalidate(self, name):
        gone = self.reverse_closure(name)
        for m in gone:
            self._mods.pop(m, None)
        return gone

    def missing(self):
        provided = set()
        need = set()
        for spec in self._mods.values():
            provided |= spec['provides']
            need |= spec['requires']
        return need - provided

    def cycles(self):
        found = set()
        colour = {}
        stack = []

        def visit(m):
            colour[m] = 1
            stack.append(m)
            for dep in sorted(self._mods[m]['requires']):
                if dep not in self._mods:
                    continue
                c = colour.get(dep, 0)
                if c == 0:
                    visit(dep)
                elif c == 1:
                    found.add(tuple(sorted(stack[stack.index(dep):])))
            stack.pop()
            colour[m] = 2

        for m in sorted(self._mods):
            if colour.get(m, 0) == 0:
                visit(m)
        return sorted(found)

    def to_json(self):
        return {m: {'provides': sorted(s['provides']),
                    'requires': sorted(s['requires'])}
                for m, s in sorted(self._mods.items())}
''',
}

REF['e22-multiprocess-shard'] = {
    'shard/worker.py': r'''
"""Resumable shard worker."""
import os


class Worker:
    def __init__(self, model, shards, out_dir, checkpoint_every=10):
        self.model = model
        self.shards = list(shards)
        self.out_dir = out_dir
        self.checkpoint_every = max(1, checkpoint_every)
        self.total_inferred = 0
        self.skipped = 0
        self._done = []
        self._failed = []
        os.makedirs(out_dir, exist_ok=True)
        self._load_state()

    # -- paths -------------------------------------------------------------
    def _out(self, sid):
        return os.path.join(self.out_dir, str(sid) + '.txt')

    def _done_path(self):
        return os.path.join(self.out_dir, 'done.txt')

    def _fail_path(self):
        return os.path.join(self.out_dir, 'failed.txt')

    # -- state -------------------------------------------------------------
    def _load_state(self):
        dp = self._done_path()
        if os.path.exists(dp):
            with open(dp) as f:
                self._done = [l.strip() for l in f if l.strip()]
        fp = self._fail_path()
        if os.path.exists(fp):
            with open(fp) as f:
                self._failed = [l.strip() for l in f if l.strip()]

    def _flush(self):
        with open(self._done_path(), 'w') as f:
            f.write('\n'.join(self._done) + ('\n' if self._done else ''))
        with open(self._fail_path(), 'w') as f:
            f.write('\n'.join(self._failed) + ('\n' if self._failed else ''))

    def _is_done(self, sid):
        """Recorded AND the output file is actually there."""
        return str(sid) in self._done and os.path.exists(self._out(sid))

    # -- work --------------------------------------------------------------
    def _one(self, sid):
        self.total_inferred += 1          # every infer CALL is counted
        try:
            text = self.model.infer(str(sid))
        except Exception:
            if str(sid) not in self._failed:
                self._failed.append(str(sid))
            return False
        with open(self._out(sid), 'w') as f:
            f.write(text)
        if str(sid) not in self._done:
            self._done.append(str(sid))
        if str(sid) in self._failed:
            self._failed.remove(str(sid))
        return True

    def run(self):
        since = 0
        self.skipped = 0
        for sid in self.shards:
            if self._is_done(sid):
                # finished by an EARLIER run: nothing to re-infer
                self.skipped += 1
                continue
            self._one(sid)
            since += 1
            if since >= self.checkpoint_every:
                self._flush()
                since = 0
        self._flush()
        return self.stats()

    def retry_failed(self):
        fixed = 0
        for sid in list(self._failed):
            if self._one(sid):
                fixed += 1
        self._flush()
        return fixed

    def stats(self):
        return {'total': len(self.shards),
                'done': sum(1 for s in self.shards if self._is_done(s)),
                'skipped': self.skipped,
                'failed': len(self._failed)}
''',
}

REF["e23-config-layers"] = {
    "cfgx/merge.py": '''
"""Config merge with list policies and a deletion sentinel."""
import copy
from types import MappingProxyType


class _Drop:
    def __repr__(self):
        return 'DROP'


DROP = _Drop()


def _merge_into(base, layer, lists):
    for k, v in layer.items():
        if v is DROP:
            base.pop(k, None)
            continue
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge_into(base[k], v, lists)
        elif isinstance(v, list) and isinstance(base.get(k), list):
            if lists == 'concat':
                base[k] = base[k] + v
            elif lists == 'unique':
                seen = set()
                out = []
                for x in base[k] + v:
                    key = repr(x)
                    if key not in seen:
                        seen.add(key)
                        out.append(x)
                base[k] = out
            else:
                base[k] = copy.deepcopy(v)
        else:
            base[k] = copy.deepcopy(v)
    return base


def merge(base, *layers, lists='replace'):
    out = copy.deepcopy(base)
    for layer in layers:
        # dotted-path DROPs are applied after the structural merge
        dotted = {k: v for k, v in layer.items() if '.' in k}
        plain = {k: v for k, v in layer.items() if '.' not in k}
        if plain:
            _merge_into(out, plain, lists)
        for path, val in dotted.items():
            if val is not DROP:
                _dotted_set(out, path, val)
    return out


def _dotted_set(cfg, path, value):
    parts = path.split('.')
    cur = cfg
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def _dotted_del(cfg, path):
    parts = path.split('.')
    cur = cfg
    for p in parts[:-1]:
        if not isinstance(cur, dict) or p not in cur:
            return
        cur = cur[p]
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)


def deep_get(cfg, path, default=None):
    cur = cfg
    for part in path.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def deep_set(cfg, path, value):
    out = copy.deepcopy(cfg)
    _dotted_set(out, path, value)
    return out


def freeze(cfg):
    if isinstance(cfg, dict):
        return MappingProxyType({k: freeze(v) for k, v in cfg.items()})
    if isinstance(cfg, list):
        return tuple(freeze(v) for v in cfg)
    return cfg
''',
}

REF['e24-fsm-parallel'] = {
    'pfsm/machine.py': r'''
"""State machine with guards, actions and parallel regions."""


class UnknownState(Exception):
    pass


class GuardFailed(Exception):
    pass


class NotParallel(Exception):
    pass


class Machine:
    def __init__(self, initial, states, on_transition=None):
        self.initial = initial
        self.states = states
        self.on_transition = on_transition
        self.state = initial
        self._history = [initial]
        self._finished = set()      # branches that completed their whole path
        self._region = None         # parallel region still open, if any
        self._arm = None            # the branch of _region we are currently on

    # -- introspection -----------------------------------------------------
    @property
    def history(self):
        """A COPY of the visited states, oldest first."""
        return list(self._history)

    @history.setter
    def history(self, value):
        self._history = list(value)

    def _spec(self, state):
        return self.states.get(state, [])

    def _branches(self, region):
        return self.states[region]['parallel']

    def _is_parallel(self, state):
        spec = self._spec(state)
        return isinstance(spec, dict) and 'parallel' in spec

    def _is_terminal(self, state):
        spec = self._spec(state)
        if isinstance(spec, dict):
            return False
        return not spec

    def _entry_for(self, src, target):
        """The declared transition src -> target as a dict, or None."""
        # While a region is open, ANY branch may be entered from anywhere
        # inside it - that is what lets one machine walk both arms of a fork.
        if self._region is not None and target in self._branches(self._region):
            return {'to': target}
        spec = self._spec(src)
        if self._is_parallel(src):
            return {'to': target} if target in spec['parallel'] else None
        for t in spec:
            if isinstance(t, dict):
                if t.get('to') == target:
                    return t
            elif t == target:
                return {'to': target}
        return None

    def _close_region_if_done(self):
        """Close the open region once every branch has finished its path."""
        if self._region is None:
            return
        if all(b in self._finished for b in self._branches(self._region)):
            self._region = None
            self._arm = None

    # -- transitions -------------------------------------------------------
    def go(self, target, **ctx):
        entry = self._entry_for(self.state, target)
        if entry is None or target not in self.states:
            raise UnknownState(f"{self.state} -> {target}")
        guard = entry.get('guard')
        if guard is not None and not guard(**ctx):
            raise GuardFailed(f"{self.state} -> {target}")
        src = self.state
        self.state = target
        self._history.append(target)
        if self._is_parallel(src):
            self._region = src
        if self._region is not None and target in self._branches(self._region):
            self._arm = target          # we are now on this branch
        done_arm = None
        if self._is_terminal(target):
            # the BRANCH finished, not just the state we came from
            done_arm = self._arm if self._arm is not None else src
            self._finished.add(done_arm)
        action = entry.get('action')
        if action is None:
            result = None
        else:
            try:
                result = action(target)
            except BaseException:
                self.state = src
                self._history.pop()
                if done_arm is not None:
                    self._finished.discard(done_arm)
                raise
        if self.on_transition is not None:
            self.on_transition(src, target)
        self._close_region_if_done()
        return target if result is None else result

    def join(self, name):
        """True once every branch of the parallel region `name` is finished."""
        if not self._is_parallel(name):
            raise NotParallel(name)
        return all(b in self._finished for b in self._branches(name))
''',
}


def main():
    doc = json.load(open(PACK))
    tasks = doc["tasks"]
    fails = []
    print(f"selftest: {len(tasks)} tasks in {os.path.relpath(PACK, ROOT)}\n")
    for t in tasks:
        tid = t["id"]
        kit = t["kit"]
        check = t["check"]

        # 1. the shipped broken kit must FAIL
        ok_neg, why_neg = run_check(kit, {}, check, timeout=t.get("timeout", 300))
        if ok_neg is not False:
            fails.append(f"{tid}: kit-as-shipped {'PASSED' if ok_neg else 'timed out'} "
                         f"(task tests nothing) - {why_neg}")
            print(f"  FAIL {tid:28s} kit-as-shipped did not fail: {why_neg}")
            continue

        # 2. the reference solution must PASS
        ref = REF.get(tid)
        if ref is None:
            fails.append(f"{tid}: NO REFERENCE SOLUTION in selftest")
            print(f"  FAIL {tid:28s} no reference solution")
            continue
        ok_pos, why_pos = run_check(kit, ref, check, timeout=t.get("timeout", 300))
        if ok_pos is not True:
            fails.append(f"{tid}: reference solution FAILED ({why_pos}) - task may be impossible")
            print(f"  FAIL {tid:28s} reference failed: {why_pos}")
            continue

        # 3. grader: a model that emits nothing must score no-file-blocks
        empty = extract_files("I cannot help with that.")
        if empty:
            fails.append(f"{tid}: prose answer parsed as file blocks {list(empty)}")
            print(f"  FAIL {tid:28s} prose parsed as files")
            continue

        # 4. the reference, wrapped in ```file blocks, must be extracted and pass
        wrapped = "\n\n".join(
            f"```file {rel}\n{content}\n```" for rel, content in sorted(ref.items()))
        got = extract_files(wrapped)
        if set(got) != set(ref):
            fails.append(f"{tid}: round-trip lost files: {sorted(got)} vs {sorted(ref)}")
            print(f"  FAIL {tid:28s} block round-trip lost files")
            continue
        ok_rt, why_rt = run_check(kit, got, check, timeout=t.get("timeout", 300))
        if ok_rt is not True:
            fails.append(f"{tid}: ```file round-trip FAILED ({why_rt})")
            print(f"  FAIL {tid:28s} file-block round-trip failed: {why_rt}")
            continue

        print(f"  ok   {tid:28s} kit fails, reference passes, blocks round-trip")

    print()
    if fails:
        print(f"SELFTEST FAIL: {len(fails)} problem(s)")
        for f in fails:
            print(f"  - {f}")
        return 1
    print(f"SELFTEST PASS: all {len(tasks)} tasks are sound "
          f"(broken kit fails, reference passes, file blocks round-trip)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
