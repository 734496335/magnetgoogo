import pathlib
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

root = pathlib.Path(__file__).resolve().parents[1]
schema = (root / 'migrations' / '0001_analytics_ops_index.sql').read_text(encoding='utf-8')
schema2 = (root / 'migrations' / '0002_ops_install_key_unique.sql').read_text(encoding='utf-8')
schema3 = (root / 'migrations' / '0003_ops_device_latest.sql').read_text(encoding='utf-8')
schema4 = (root / 'migrations' / '0004_ops_device_latest_day_index.sql').read_text(encoding='utf-8')
schema5 = (root / 'migrations' / '0005_growth_north_star_indexes.sql').read_text(encoding='utf-8')
schema6 = (root / 'migrations' / '0006_ops_device_aliases_exact_authority.sql').read_text(encoding='utf-8')
assert 'CREATE TRIGGER' not in schema.upper(), 'D1 migration must not rely on trigger bodies'
assert 'UNIQUE INDEX' in schema2.upper() and 'INSTALL_KEY' in schema2.upper(), 'install_id must be globally unique'
assert 'OPS_DEVICE_LATEST' in schema3.upper(), 'latest-device version read model missing'
assert 'IDX_OPS_DEVICE_LATEST_LAST_SEEN_TS' in schema3.upper(), 'latest-device timestamp index missing'
assert 'LAST_SEEN_DAY' in schema4.upper() and 'IDX_OPS_DEVICE_LATEST_LAST_SEEN_DAY' in schema4.upper(), 'operational-day version index migration missing'
assert 'IDX_OPS_DEVICE_DAYS_DEVICE_DAY_ACTION' in schema5.upper(), 'north-star device/day/action index missing'
assert 'IDX_OPS_SEARCHES_SUBMITTED_ACTION_COMPLETED' in schema5.upper(), 'search-satisfaction index missing'
assert 'OPS_DEVICE_ALIASES' in schema6.upper() and 'OPS_DEVICE_DAYS_EXACT' in schema6.upper(), 'canonical device authority migration missing'
assert 'CONFLICT' in schema6.upper(), 'ambiguous aliases must fail open to separate identities rather than force-merge'


def ensure_day(db, day):
    db.execute("INSERT INTO ops_daily(day) VALUES (?) ON CONFLICT(day) DO NOTHING", (day,))


def upsert_latest_device(db, device_key, last_seen_ts, app_v, version_code=''):
    last_seen_day = (datetime.fromtimestamp(last_seen_ts / 1000, timezone.utc) + timedelta(hours=8)).date().isoformat()
    db.execute(
        "INSERT INTO ops_device_latest(device_key,last_seen_ts,last_seen_day,app_v,version_code,country) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(device_key) DO UPDATE SET "
        "last_seen_ts=excluded.last_seen_ts,last_seen_day=excluded.last_seen_day,"
        "app_v=CASE WHEN excluded.app_v<>'' THEN excluded.app_v ELSE ops_device_latest.app_v END,"
        "version_code=CASE WHEN excluded.version_code<>'' THEN excluded.version_code ELSE ops_device_latest.version_code END "
        "WHERE excluded.last_seen_day>ops_device_latest.last_seen_day "
        "OR (excluded.last_seen_day=ops_device_latest.last_seen_day AND excluded.last_seen_ts>ops_device_latest.last_seen_ts AND ((excluded.app_v<>'' AND excluded.app_v<>ops_device_latest.app_v) OR (excluded.version_code<>'' AND excluded.version_code<>ops_device_latest.version_code)))",
        (device_key, last_seen_ts, last_seen_day, app_v, version_code, 'CN'),
    )


def upsert_device(db, day, device_key, first_ts, searched=0, got_result=0, action=0, country='CN'):
    ensure_day(db, day)
    db.execute(
        "UPDATE ops_daily SET "
        "active_devices=active_devices+CASE WHEN NOT EXISTS(SELECT 1 FROM ops_device_days WHERE day=? AND device_key=?) THEN 1 ELSE 0 END,"
        "search_devices=search_devices+CASE WHEN ?=1 AND NOT EXISTS(SELECT 1 FROM ops_device_days WHERE day=? AND device_key=? AND searched=1) THEN 1 ELSE 0 END,"
        "result_devices=result_devices+CASE WHEN ?=1 AND NOT EXISTS(SELECT 1 FROM ops_device_days WHERE day=? AND device_key=? AND got_result=1) THEN 1 ELSE 0 END,"
        "action_devices=action_devices+CASE WHEN ?=1 AND NOT EXISTS(SELECT 1 FROM ops_device_days WHERE day=? AND device_key=? AND action=1) THEN 1 ELSE 0 END "
        "WHERE day=? AND (NOT EXISTS(SELECT 1 FROM ops_device_days WHERE day=? AND device_key=?) "
        "OR (?=1 AND NOT EXISTS(SELECT 1 FROM ops_device_days WHERE day=? AND device_key=? AND searched=1)) "
        "OR (?=1 AND NOT EXISTS(SELECT 1 FROM ops_device_days WHERE day=? AND device_key=? AND got_result=1)) "
        "OR (?=1 AND NOT EXISTS(SELECT 1 FROM ops_device_days WHERE day=? AND device_key=? AND action=1)))",
        (
            day, device_key, searched, day, device_key, got_result, day, device_key, action, day, device_key,
            day, day, device_key, searched, day, device_key, got_result, day, device_key, action, day, device_key,
        ),
    )
    db.execute(
        "INSERT INTO ops_device_days(day,device_key,first_event_ts,app_v,country,searched,got_result,action) VALUES(?,?,?,?,?,?,?,?) "
        "ON CONFLICT(day,device_key) DO UPDATE SET first_event_ts=MIN(ops_device_days.first_event_ts,excluded.first_event_ts),"
        "searched=MAX(ops_device_days.searched,excluded.searched),got_result=MAX(ops_device_days.got_result,excluded.got_result),action=MAX(ops_device_days.action,excluded.action) "
        "WHERE excluded.first_event_ts<ops_device_days.first_event_ts OR excluded.searched>ops_device_days.searched "
        "OR excluded.got_result>ops_device_days.got_result OR excluded.action>ops_device_days.action",
        (day, device_key, first_ts, '0.2.7', country, searched, got_result, action),
    )


def insert_unique(db, table, day_col, key_col, counter, day, key, insert_sql, values):
    ensure_day(db, day)
    db.execute(
        f"UPDATE ops_daily SET {counter}={counter}+CASE WHEN NOT EXISTS(SELECT 1 FROM {table} WHERE {day_col}=? AND {key_col}=?) THEN 1 ELSE 0 END WHERE day=?",
        (day, key, day),
    )
    db.execute(insert_sql, values)


def upsert_install(db, install_day, install_key, installation_ts, first_open_ts):
    ensure_day(db, install_day)
    db.execute(
        "UPDATE ops_daily SET physical_installs=MAX(0,physical_installs-1) "
        "WHERE day=(SELECT install_day FROM ops_install_days WHERE install_key=? AND installation_ts>? LIMIT 1) AND day<>?",
        (install_key, installation_ts, install_day),
    )
    db.execute(
        "UPDATE ops_daily SET physical_installs=physical_installs+CASE "
        "WHEN NOT EXISTS(SELECT 1 FROM ops_install_days WHERE install_key=?) "
        "OR EXISTS(SELECT 1 FROM ops_install_days WHERE install_key=? AND installation_ts>? AND install_day<>?) THEN 1 ELSE 0 END WHERE day=?",
        (install_key, install_key, installation_ts, install_day, install_day),
    )
    db.execute(
        "INSERT INTO ops_install_days(install_day,install_key,installation_ts,first_open_ts,app_v,country) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(install_key) DO UPDATE SET "
        "install_day=CASE WHEN excluded.installation_ts<ops_install_days.installation_ts THEN excluded.install_day ELSE ops_install_days.install_day END,"
        "installation_ts=MIN(ops_install_days.installation_ts,excluded.installation_ts),"
        "first_open_ts=MIN(ops_install_days.first_open_ts,excluded.first_open_ts)",
        (install_day, install_key, installation_ts, first_open_ts, '0.2.7', 'CN'),
    )


def upsert_search(db, search_id, submitted_day=None, submitted_ts=None, completed_day=None, completed_ts=None, result_count=None):
    if submitted_ts is not None and submitted_day:
        ensure_day(db, submitted_day)
        db.execute(
            "UPDATE ops_daily SET searches_submitted=searches_submitted+CASE WHEN NOT EXISTS(SELECT 1 FROM ops_searches WHERE search_id=? AND submitted_ts IS NOT NULL) THEN 1 ELSE 0 END WHERE day=?",
            (search_id, submitted_day),
        )
    if completed_ts is not None and completed_day:
        ensure_day(db, completed_day)
        rc = max(0, int(result_count or 0))
        db.execute(
            "UPDATE ops_daily SET "
            "searches_completed=searches_completed+CASE WHEN NOT EXISTS(SELECT 1 FROM ops_searches WHERE search_id=? AND completed_ts IS NOT NULL) THEN 1 ELSE 0 END,"
            "searches_with_results=searches_with_results+CASE WHEN ?>0 AND NOT EXISTS(SELECT 1 FROM ops_searches WHERE search_id=? AND completed_ts IS NOT NULL) THEN 1 ELSE 0 END,"
            "zero_result_searches=zero_result_searches+CASE WHEN ?=0 AND NOT EXISTS(SELECT 1 FROM ops_searches WHERE search_id=? AND completed_ts IS NOT NULL) THEN 1 ELSE 0 END WHERE day=?",
            (search_id, rc, search_id, rc, search_id, completed_day),
        )
    db.execute(
        "INSERT INTO ops_searches(search_id,device_key,submitted_day,submitted_ts,completed_day,completed_ts,result_count,ttfr_ms,action,app_v,country) VALUES(?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(search_id) DO UPDATE SET "
        "submitted_day=CASE WHEN ops_searches.submitted_ts IS NULL OR (excluded.submitted_ts IS NOT NULL AND excluded.submitted_ts<ops_searches.submitted_ts) THEN excluded.submitted_day ELSE ops_searches.submitted_day END,"
        "submitted_ts=CASE WHEN ops_searches.submitted_ts IS NULL OR (excluded.submitted_ts IS NOT NULL AND excluded.submitted_ts<ops_searches.submitted_ts) THEN excluded.submitted_ts ELSE ops_searches.submitted_ts END,"
        "completed_day=CASE WHEN ops_searches.completed_ts IS NULL OR (excluded.completed_ts IS NOT NULL AND excluded.completed_ts>=ops_searches.completed_ts) THEN excluded.completed_day ELSE ops_searches.completed_day END,"
        "completed_ts=CASE WHEN ops_searches.completed_ts IS NULL OR (excluded.completed_ts IS NOT NULL AND excluded.completed_ts>=ops_searches.completed_ts) THEN excluded.completed_ts ELSE ops_searches.completed_ts END,"
        "result_count=CASE WHEN excluded.completed_ts IS NOT NULL AND (ops_searches.completed_ts IS NULL OR excluded.completed_ts>=ops_searches.completed_ts) THEN excluded.result_count ELSE ops_searches.result_count END",
        (search_id, 'dev-a', submitted_day, submitted_ts, completed_day, completed_ts, result_count, 650, 0, '0.2.7', 'CN'),
    )


with tempfile.TemporaryDirectory() as tmpdir:
    db_path = pathlib.Path(tmpdir) / 'ops.sqlite'
    db = sqlite3.connect(db_path)
    db.executescript(schema)
    db.executescript(schema)  # base migration must be safely replayable before d1_migrations is marked
    db.executescript(schema2)
    db.executescript(schema2)  # follow-up uniqueness migration must also be replayable
    db.executescript(schema3)
    db.executescript(schema3)  # latest-version base migration must also be replayable
    db.executescript(schema4)
    db.executescript(schema5)
    db.executescript(schema5)  # growth indexes must be replay-safe
    db.executescript(schema6)
    db.executescript(schema6)  # canonical identity table/view must be replay-safe

    upsert_latest_device(db, 'dev-a', 2_000_000_000_000, '0.2.6', '206')
    upsert_latest_device(db, 'dev-a', 2_000_000_010_000, '0.2.7', '207')
    upsert_latest_device(db, 'dev-a', 1_999_999_000_000, '0.2.5', '205')
    latest = db.execute("SELECT app_v,version_code,last_seen_ts,last_seen_day FROM ops_device_latest WHERE device_key='dev-a'").fetchone()
    assert latest[:3] == ('0.2.7', '207', 2_000_000_010_000), latest
    assert latest[3], latest
    upsert_latest_device(db, 'dev-b', 2_000_000_005_000, '0.2.7', '207')
    min_version_day = (datetime.fromtimestamp(1_999_999_500_000 / 1000, timezone.utc) + timedelta(hours=8)).date().isoformat()
    version_rows = db.execute(
        "SELECT app_v,version_code,COUNT(*) FROM ops_device_latest WHERE last_seen_day>=? GROUP BY app_v,version_code ORDER BY COUNT(*) DESC",
        (min_version_day,),
    ).fetchall()
    assert version_rows == [('0.2.7', '207', 2)], version_rows

    # Canonical identity: two legacy installation IDs from the same proven
    # android_id_hash device must collapse to one device-day. An ambiguous alias
    # conflict must not be force-merged.
    upsert_device(db, '2026-08-15', 'legacy-a1', 900, searched=1)
    upsert_device(db, '2026-08-15', 'legacy-a2', 950, action=1)
    db.execute("INSERT INTO ops_device_aliases(alias_key,canonical_key,kind,last_seen_ts,conflict) VALUES(?,?,?,?,0)", ('legacy-a1', 'dv2-physical-a', 'android_id_hash', 1000))
    db.execute("INSERT INTO ops_device_aliases(alias_key,canonical_key,kind,last_seen_ts,conflict) VALUES(?,?,?,?,0)", ('legacy-a2', 'dv2-physical-a', 'android_id_hash', 1000))
    exact_alias = db.execute("SELECT COUNT(*),SUM(searched),SUM(action) FROM ops_device_days_exact WHERE day='2026-08-15'").fetchone()
    assert exact_alias == (1, 1, 1), exact_alias
    upsert_device(db, '2026-08-15', 'legacy-conflict', 970)
    db.execute("INSERT INTO ops_device_aliases(alias_key,canonical_key,kind,last_seen_ts,conflict) VALUES(?,?,?,?,1)", ('legacy-conflict', 'dv2-uncertain', 'android_id_hash', 1000))
    exact_alias = db.execute("SELECT COUNT(*) FROM ops_device_days_exact WHERE day='2026-08-15'").fetchone()
    assert exact_alias == (2,), exact_alias

    upsert_device(db, '2026-08-29', 'dev-a', 1000)
    upsert_device(db, '2026-08-29', 'dev-a', 1100, searched=1, got_result=1, action=1)
    row = db.execute("SELECT active_devices,search_devices,result_devices,action_devices FROM ops_daily WHERE day='2026-08-29'").fetchone()
    assert row == (1, 1, 1, 1), row
    upsert_device(db, '2026-08-29', 'dev-a', 1200, searched=1, got_result=1, action=1)
    row = db.execute("SELECT active_devices,search_devices,result_devices,action_devices FROM ops_daily WHERE day='2026-08-29'").fetchone()
    assert row == (1, 1, 1, 1), row

    upsert_install(db, '2026-08-29', 'install-a', 2_000_000_000_000, 2_000_000_001_000)
    upsert_install(db, '2026-08-29', 'install-a', 2_000_000_000_000, 2_000_000_001_000)
    # Same install_id observed later with an earlier valid installation timestamp must move,
    # not count as a second physical installation on a second day.
    upsert_install(db, '2026-08-28', 'install-a', 1_999_900_000_000, 2_000_000_001_000)
    insert_unique(
        db, 'ops_session_days', 'day', 'session_id', 'sessions', '2026-08-29', 'sess-a',
        "INSERT OR IGNORE INTO ops_session_days VALUES(?,?,?,?,?,?)", ('2026-08-29', 'sess-a', 'dev-a', 1000, '0.2.7', 'CN'),
    )
    insert_unique(
        db, 'ops_session_days', 'day', 'session_id', 'sessions', '2026-08-29', 'sess-a',
        "INSERT OR IGNORE INTO ops_session_days VALUES(?,?,?,?,?,?)", ('2026-08-29', 'sess-a', 'dev-a', 1000, '0.2.7', 'CN'),
    )
    row = db.execute("SELECT physical_installs,sessions FROM ops_daily WHERE day='2026-08-29'").fetchone()
    assert row == (0, 1), row
    row = db.execute("SELECT physical_installs FROM ops_daily WHERE day='2026-08-28'").fetchone()
    assert row == (1,), row
    install_rows = db.execute("SELECT install_day,install_key FROM ops_install_days WHERE install_key='install-a'").fetchall()
    assert install_rows == [('2026-08-28', 'install-a')], install_rows

    upsert_search(db, 'search-a', completed_day='2026-08-29', completed_ts=2000, result_count=12)
    upsert_search(db, 'search-a', submitted_day='2026-08-29', submitted_ts=1500)
    upsert_search(db, 'search-a', submitted_day='2026-08-29', submitted_ts=1400, completed_day='2026-08-29', completed_ts=2100, result_count=12)
    row = db.execute("SELECT searches_submitted,searches_completed,searches_with_results,zero_result_searches FROM ops_daily WHERE day='2026-08-29'").fetchone()
    assert row == (1, 1, 1, 0), row

    upsert_search(db, 'search-b', submitted_day='2026-08-29', submitted_ts=2200, completed_day='2026-08-29', completed_ts=2300, result_count=0)
    upsert_search(db, 'search-b', submitted_day='2026-08-29', submitted_ts=2200, completed_day='2026-08-29', completed_ts=2300, result_count=0)
    row = db.execute("SELECT searches_submitted,searches_completed,searches_with_results,zero_result_searches FROM ops_daily WHERE day='2026-08-29'").fetchone()
    assert row == (2, 2, 1, 1), row

    # Growth north star: DSSU is device-level Magnet Action, independent of whether
    # an exhaustive search_completed terminal was emitted. CN and international
    # segments stay separate, and D7 returning requires satisfaction on both days.
    upsert_device(db, '2026-08-16', 'growth-return-us', 3000, searched=1, got_result=1, action=1, country='US')
    upsert_device(db, '2026-08-23', 'growth-return-us', 4000, searched=1, got_result=1, action=1, country='US')
    upsert_device(db, '2026-08-23', 'growth-new-cn', 4100, searched=1, got_result=1, action=1, country='CN')
    upsert_device(db, '2026-08-23', 'growth-search-cn', 4200, searched=1, got_result=1, action=0, country='CN')
    growth_rows = db.execute(
        "SELECT d.day,CASE WHEN d.country='CN' THEN 'cn' WHEN d.country='' THEN 'unknown' ELSE 'intl' END AS segment,"
        "COUNT(*) AS active_devices,SUM(d.searched),SUM(d.got_result),SUM(d.action),"
        "SUM(CASE WHEN NOT EXISTS(SELECT 1 FROM ops_device_days f WHERE f.device_key=d.device_key AND f.day<d.day) THEN 1 ELSE 0 END),"
        "SUM(CASE WHEN d.action=1 AND NOT EXISTS(SELECT 1 FROM ops_device_days f WHERE f.device_key=d.device_key AND f.day<d.day) THEN 1 ELSE 0 END),"
        "SUM(CASE WHEN d.action=1 AND EXISTS(SELECT 1 FROM ops_device_days p WHERE p.device_key=d.device_key AND p.day=date(d.day,'-7 day') AND p.action=1) THEN 1 ELSE 0 END) "
        "FROM ops_device_days d WHERE d.day='2026-08-23' GROUP BY d.day,segment ORDER BY segment"
    ).fetchall()
    assert ('2026-08-23', 'cn', 2, 2, 2, 1, 2, 1, 0) in growth_rows, growth_rows
    assert ('2026-08-23', 'intl', 1, 1, 1, 1, 0, 0, 1) in growth_rows, growth_rows

    upsert_search(db, 'search-satisfied-no-complete', submitted_day='2026-08-23', submitted_ts=5000)
    db.execute("UPDATE ops_searches SET action=1 WHERE search_id='search-satisfied-no-complete'")
    funnel = db.execute(
        "SELECT COUNT(*),SUM(CASE WHEN completed_ts IS NOT NULL THEN 1 ELSE 0 END),SUM(CASE WHEN action=1 THEN 1 ELSE 0 END),SUM(CASE WHEN action=1 AND completed_ts IS NULL THEN 1 ELSE 0 END) FROM ops_searches WHERE submitted_day='2026-08-23'"
    ).fetchone()
    assert funnel == (1, 0, 1, 1), funnel

    growth_plan = db.execute(
        "EXPLAIN QUERY PLAN SELECT 1 FROM ops_device_days f WHERE f.device_key=? AND f.day<? LIMIT 1",
        ('growth-return-us', '2026-08-23'),
    ).fetchall()
    assert any('idx_ops_device_days_device_day_action' in str(part) or 'PRIMARY KEY' in str(part) for plan_row in growth_plan for part in plan_row), growth_plan

    # Capacity gate: 5,000 distinct device-days remain exact; replaying one device 100 times never inflates DAU.
    capacity_day = '2026-08-30'
    for i in range(5000):
        upsert_device(db, capacity_day, f'cap-{i}', 10_000 + i)
    # Model 25 raw batches/device/day. The 24 repeated no-state-change batches
    # must execute as true SQLite no-ops rather than consuming D1 row writes.
    changes_before_repeat = db.total_changes
    for repeat in range(24):
        for i in range(5000):
            upsert_device(db, capacity_day, f'cap-{i}', 30_000 + repeat * 5000 + i)
    repeat_write_changes = db.total_changes - changes_before_repeat
    assert repeat_write_changes == 0, repeat_write_changes
    for i in range(100):
        upsert_device(db, capacity_day, 'cap-0', 200_000 + i, searched=1, got_result=1, action=1)
    row = db.execute("SELECT active_devices,search_devices,result_devices,action_devices FROM ops_daily WHERE day=?", (capacity_day,)).fetchone()
    assert row == (5000, 1, 1, 1), row
    db.execute("UPDATE ops_daily SET active_devices=active_devices+100 WHERE day=?", (capacity_day,))
    poisoned_counter = db.execute("SELECT active_devices FROM ops_daily WHERE day=?", (capacity_day,)).fetchone()[0]
    exact_authority = db.execute("SELECT COUNT(*) FROM ops_device_days_exact WHERE day=?", (capacity_day,)).fetchone()[0]
    assert poisoned_counter == 5100, poisoned_counter
    assert exact_authority == 5000, exact_authority
    plan = db.execute("EXPLAIN QUERY PLAN SELECT * FROM ops_daily WHERE day>=? ORDER BY day", ('2026-08-01',)).fetchall()
    assert any('SEARCH ops_daily' in str(part) for plan_row in plan for part in plan_row), plan
    version_plan = db.execute(
        "EXPLAIN QUERY PLAN SELECT app_v,version_code,COUNT(*) FROM ops_device_latest WHERE last_seen_day>=? GROUP BY app_v,version_code",
        (min_version_day,),
    ).fetchall()
    assert any('idx_ops_device_latest_last_seen_day' in str(part) for plan_row in version_plan for part in plan_row), version_plan

    db.close()
    print(f'PASS analytics ops D1 schema: exact rollups + 5000 DAU + 125000 repeated-batch write-noops={repeat_write_changes} + version day index + global install_id uniqueness')
