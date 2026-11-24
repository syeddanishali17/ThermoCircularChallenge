"""Scenario recipes and local or session-scoped SQLite persistence."""
import base64
import binascii
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .config import Settings
from .model import ADAPTER_VERSION, ENGINE_HASH, MAX_CSV, PROXY_VERSION, scenario_id, source_hash, validate_hourly

MAX_RECIPE = 4 * ((MAX_CSV + 2) // 3) + 12_000


def recipe(run):
    return {
        "format": "thermocircular-scenario/v1",
        "metadata": run.metadata(),
        "settings": run.settings.model_dump(),
        "hourly_csv_base64": base64.b64encode(run.payload).decode() if run.payload is not None else None,
    }


def parse_recipe(data):
    if not 0 < len(data) <= MAX_RECIPE:
        raise ValueError("Scenario JSON is empty or too large.")
    try:
        doc = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("Scenario file must be valid JSON.") from None
    if not isinstance(doc, dict) or doc.get("format") != "thermocircular-scenario/v1":
        raise ValueError("Use a ThermoCircular v1 scenario JSON export.")
    meta = doc.get("metadata")
    if not isinstance(meta, dict) or (meta.get("model_version"), meta.get("engine_sha256"),
                                     meta.get("adapter_version")) != (PROXY_VERSION, ENGINE_HASH, ADAPTER_VERSION):
        raise ValueError("This recipe requires the engine and adapter versions listed in the file.")
    settings = Settings.model_validate(doc.get("settings"))
    modules = meta.get("fixed_modules")
    if type(modules) is not int or modules not in range(3):
        raise ValueError("Scenario must select zero, one or two fixed modules.")
    encoded = doc.get("hourly_csv_base64")
    payload = None
    if encoded is not None:
        if not isinstance(encoded, str):
            raise ValueError("Invalid hourly source in scenario JSON.")
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Invalid base64 hourly source.") from None
        validate_hourly(payload)
    if (meta.get("input_sha256") != source_hash(payload)
            or meta.get("scenario_id") != scenario_id(settings, payload, modules)):
        raise ValueError("Recipe and input fingerprints do not agree.")
    return settings, payload, modules


def name_text(name):
    name = name.strip()
    if not 1 <= len(name) <= 64 or not name.isprintable():
        raise ValueError("Enter a printable scenario name with 1 to 64 characters.")
    return name


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self.memory = sqlite3.connect(":memory:", check_same_thread=False) if path is None else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS scenarios (
                    key TEXT PRIMARY KEY, name TEXT NOT NULL, created TEXT NOT NULL,
                    recipe TEXT NOT NULL, results TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS registers (
                    key TEXT PRIMARY KEY, content TEXT NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=10) if self.path is not None else self.memory
        try:
            with con:
                yield con
        finally:
            if self.path is not None:
                con.close()

    def save(self, name, run):
        name = name_text(name)
        snapshot = {"annual": run.cases, "investments": run.investments, "fixed": run.fixed,
                    "increment": run.increment, "units": "See metric suffixes and DATA_DICTIONARY.md"}
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT count(*) FROM scenarios").fetchone()[0] >= 16:
                raise ValueError("The workspace holds up to 16 scenarios. Export and remove one to save another.")
            con.execute("INSERT INTO scenarios VALUES (?, ?, ?, ?, ?)", (
                uuid4().hex, name, run.created_at, json.dumps(recipe(run), allow_nan=False),
                json.dumps(snapshot, allow_nan=False),
            ))

    def list(self):
        with self.connect() as con:
            return con.execute("SELECT key, name, created FROM scenarios ORDER BY created DESC, key").fetchall()

    def get(self, key):
        with self.connect() as con:
            row = con.execute("SELECT recipe, results FROM scenarios WHERE key = ?", (key,)).fetchone()
        if row is None:
            raise ValueError("Saved scenario is unavailable.")
        return row[0].encode(), json.loads(row[1])

    def rename(self, key, name):
        with self.connect() as con:
            con.execute("UPDATE scenarios SET name = ? WHERE key = ?", (name_text(name), key))

    def delete(self, key):
        with self.connect() as con:
            con.execute("DELETE FROM scenarios WHERE key = ?", (key,))

    def register(self, key, default):
        with self.connect() as con:
            row = con.execute("SELECT content FROM registers WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def save_register(self, key, data):
        raw = json.dumps(data, allow_nan=False)
        if len(raw) > 250_000:
            raise ValueError("Register exceeds 250 KB.")
        with self.connect() as con:
            con.execute("INSERT INTO registers VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET content=excluded.content",
                        (key, raw))
