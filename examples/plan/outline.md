# Caching in three minutes

Why the fastest request is the one you never make.

Your app feels slow, and the database is usually why. A cache can make the same page 40x faster.

## Why cache at all

Every request that reaches the database costs time and money. A cache keeps recent answers close to the code that needs them.

- Speed
- Cost
- Scale

Answers come back in microseconds instead of milliseconds. Fewer queries mean a smaller database bill. And the same servers can handle far more users.

## How a cache works

A request asks the cache first, and only a miss goes on to the database.

Request -> Cache -> Database

On the way back the answer is stored, so the next request for it is a hit.

### Cache-aside, step by step

1. Look up the key in the cache
2. On a miss, query the database
3. Store the result with an expiry time
4. Return the value to the caller

### How far away is your data?

| Where | Read time |
|---|---|
| In-process memory | 0.1 ms |
| Redis | 1 ms |
| Database | 25 ms |
| Remote API | 250 ms |

Every hop away from your code makes a read about ten times slower. A call to a remote API is the slowest of all.

### What a hit rate buys you

With a hit rate of 90%, the average read drops from 25 milliseconds to about 3.

$$t = h \cdot t_{cache} + (1 - h) \cdot t_{db}$$

### In code

Python ships a cache in its standard library.

```python
from functools import lru_cache

@lru_cache(maxsize=1024)
def get_user(user_id):
    return db.query("SELECT * FROM users WHERE id = %s", user_id)
```

One decorator keeps the last thousand users in memory.

## Where to keep the cache

### Local memory vs Redis

Local memory:

- Fastest possible reads
- Lost on every restart
- One copy per server

Redis:

- Shared by every server
- Survives restarts
- One network hop away

Local memory is the fastest place to keep a value, but every server holds its own copy. Redis is shared by all of them, at the price of one network hop.

### When not to cache

Some data should never be cached. Account balances and stock levels must always be exact. Data that changes on every request gains nothing from a cache. And a cache you cannot measure is a bug waiting to happen.

## The hard part

> There are only two hard things in Computer Science: cache invalidation and naming things.
> — Phil Karlton

Stale data is the price of speed. Give every entry an expiry time, and delete it when the source changes. When many entries expire at once, add a little random jitter so they do not all hit the database together.

## Summary

- Cache what is read often and changes rarely
- Measure your hit rate
- Always set an expiry time

Start with one slow endpoint this week. The full example is on [GitHub](https://github.com/example/caching-demo).
