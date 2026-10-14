"""Owner-bound, expiring, one-use Google Docs edit proposals."""
import secrets
import time

class DocFixPending:
    def __init__(self, ttl_seconds=600, limit=12, clock=time.monotonic):
        self.ttl, self.limit, self.clock = ttl_seconds, limit, clock
        self._entries = {}

    def _expire(self):
        now = self.clock()
        for token, (expires, _, _) in tuple(self._entries.items()):
            if expires <= now:
                self._entries.pop(token, None)

    def create(self, user_id, payload):
        self._expire()
        if len(self._entries) >= self.limit:
            raise ValueError("Too many pending document previews.")
        token = secrets.token_urlsafe(24)
        self._entries[token] = (self.clock() + self.ttl, int(user_id), payload)
        return token

    def take(self, user_id, token):
        self._expire()
        record = self._entries.get(token)
        if not record or record[1] != int(user_id):
            return None
        self._entries.pop(token, None)
        return record[2]

    def forget(self, user_id):
        for token, (_, owner, _) in tuple(self._entries.items()):
            if owner == int(user_id):
                self._entries.pop(token, None)
