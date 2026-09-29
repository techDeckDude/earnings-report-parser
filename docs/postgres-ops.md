# Postgres Operations Runbook

## Diagnosing blocked queries / stuck migrations

### Symptom
`init_db()` hangs indefinitely, or any `ALTER TABLE` call never returns.
Common trigger: a previous Python process was killed mid-transaction (Ctrl-C,
kill, crash) without committing or rolling back, leaving its connection in
`idle in transaction` state.

### Why it blocks
`ALTER TABLE` requires an **exclusive lock** on the table. Any open transaction —
even one sitting completely idle — holds shared locks on every table it touched.
Postgres will queue the `ALTER TABLE` behind it forever until the connection
is terminated or the transaction ends.

### Diagnose with pg_stat_activity

```sql
SELECT
  pid,
  state,
  wait_event_type,
  wait_event,
  now() - query_start AS duration,
  left(query, 100) AS query_preview
FROM pg_stat_activity
WHERE datname = 'appdb'
ORDER BY duration DESC NULLS LAST;
```

Look for:

* `state = 'idle in transaction'` — an open transaction doing nothing
* `wait_event_type = 'Lock'` — a query waiting to acquire a lock
* `wait_event = 'relation'` — specifically waiting on a table lock

The `idle in transaction` row with the longest duration is almost always
the root cause. Everything else is queued behind it.

### Fix: terminate the blocking connection

```sql
SELECT pg_terminate_backend(<pid>);
```

To terminate all idle-in-transaction connections at once:

```sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'appdb'
  AND state = 'idle in transaction'
  AND now() - query_start > interval '5 minutes';
```

### Prevention
Wherever possible, open DB connections inside a `with` block or use a
connection pool with a short `idle_in_transaction_session_timeout`. For
one-off CLI scripts, call `conn.close()` in a `finally` block so a Ctrl-C
doesn't leak an open transaction.
