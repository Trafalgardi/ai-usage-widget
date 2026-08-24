# -*- coding: utf-8 -*-
"""Local application settings storage with atomic replacement."""

import copy
import json
import os


def _merge(base, user):
    result = copy.deepcopy(base)
    for key, value in (user or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


class ConfigStore:
    def __init__(self, path, defaults):
        self.path = path
        self.defaults = copy.deepcopy(defaults)

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as stream:
                user = json.load(stream)
            if not isinstance(user, dict):
                return copy.deepcopy(self.defaults)
            return _merge(self.defaults, user)
        except (OSError, json.JSONDecodeError):
            return copy.deepcopy(self.defaults)

    def save(self, value):
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        temporary = self.path + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as stream:
                json.dump(value, stream, indent=2, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            return True
        finally:
            try:
                if os.path.exists(temporary):
                    os.remove(temporary)
            except OSError:
                pass

    def migrate_from(self, legacy_path):
        """Copy a valid legacy config once; never delete or rewrite the source."""
        if os.path.abspath(legacy_path) == os.path.abspath(self.path):
            return False
        if os.path.exists(self.path) or not os.path.isfile(legacy_path):
            return False
        try:
            with open(legacy_path, "r", encoding="utf-8") as stream:
                value = json.load(stream)
            if not isinstance(value, dict):
                return False
            return self.save(_merge(self.defaults, value))
        except (OSError, json.JSONDecodeError):
            return False
