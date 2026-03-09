from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import Dict, Iterable, Iterator, List

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row


load_dotenv()


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return database_url


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    connection = psycopg.connect(get_database_url(), row_factory=dict_row)
    try:
        yield connection
    finally:
        connection.close()


def fetch_active_candidate_rows(connection: psycopg.Connection) -> List[Dict]:
    query = """
        SELECT
            js.id AS job_seeker_id,
            jsp.years_of_experience,
            s.name AS skill_name,
            jss.verified
        FROM job_seekers js
        INNER JOIN job_seeker_profiles jsp
            ON jsp.job_seeker_id = js.id
        LEFT JOIN job_seeker_skills jss
            ON jss.job_seeker_id = js.id
        LEFT JOIN skills s
            ON s.id = jss.skill_id
        WHERE js.is_active = TRUE
        ORDER BY js.id
    """
    with connection.cursor() as cursor:
        cursor.execute(query)
        return list(cursor.fetchall())


def fetch_direct_job_rows(connection: psycopg.Connection, job_id: str) -> List[Dict]:
    query = """
        SELECT
            dj.id AS job_id,
            dj.experience_level,
            s.name AS skill_name
        FROM direct_jobs dj
        LEFT JOIN direct_job_skills djs
            ON djs.job_id = dj.id
        LEFT JOIN skills s
            ON s.id = djs.skill_id
        WHERE dj.id = %(job_id)s
          AND dj.status = 'PUBLISHED'
        ORDER BY dj.id
    """
    with connection.cursor() as cursor:
        cursor.execute(query, {"job_id": job_id})
        return list(cursor.fetchall())


def fetch_scraped_job_rows(
    connection: psycopg.Connection,
    since: datetime,
    until: datetime,
) -> List[Dict]:
    query = """
        SELECT
            sj.id AS job_id,
            sj.updated_at,
            s.name AS skill_name
        FROM scraped_jobs sj
        LEFT JOIN scraped_job_skills sjs
            ON sjs.job_id = sj.id
        LEFT JOIN skills s
            ON s.id = sjs.skill_id
        WHERE sj.updated_at >= %(since)s
          AND sj.updated_at < %(until)s
        ORDER BY sj.updated_at, sj.id
    """
    with connection.cursor() as cursor:
        cursor.execute(query, {"since": since, "until": until})
        return list(cursor.fetchall())


def upsert_direct_matches(
    connection: psycopg.Connection,
    rows: Iterable[Dict[str, Decimal]],
) -> int:
    params = [
        {
            "id": str(uuid.uuid4()),
            "direct_job_id": row["direct_job_id"],
            "job_seeker_id": row["job_seeker_id"],
            "match_score": row["match_score"],
        }
        for row in rows
    ]
    if not params:
        return 0

    query = """
        INSERT INTO direct_job_matches (
            id,
            direct_job_id,
            job_seeker_id,
            match_score,
            created_at,
            updated_at
        )
        VALUES (
            %(id)s,
            %(direct_job_id)s,
            %(job_seeker_id)s,
            %(match_score)s,
            NOW(),
            NOW()
        )
        ON CONFLICT (direct_job_id, job_seeker_id)
        DO UPDATE SET
            match_score = EXCLUDED.match_score,
            updated_at = NOW()
    """
    with connection.cursor() as cursor:
        cursor.executemany(query, params)
    connection.commit()
    return len(params)


def upsert_scraped_matches(
    connection: psycopg.Connection,
    rows: Iterable[Dict[str, Decimal]],
) -> int:
    params = [
        {
            "id": str(uuid.uuid4()),
            "scraped_job_id": row["scraped_job_id"],
            "job_seeker_id": row["job_seeker_id"],
            "match_score": row["match_score"],
        }
        for row in rows
    ]
    if not params:
        return 0

    query = """
        INSERT INTO scraped_job_matches (
            id,
            scraped_job_id,
            job_seeker_id,
            match_score,
            created_at,
            updated_at
        )
        VALUES (
            %(id)s,
            %(scraped_job_id)s,
            %(job_seeker_id)s,
            %(match_score)s,
            NOW(),
            NOW()
        )
        ON CONFLICT (scraped_job_id, job_seeker_id)
        DO UPDATE SET
            match_score = EXCLUDED.match_score,
            updated_at = NOW()
    """
    with connection.cursor() as cursor:
        cursor.executemany(query, params)
    connection.commit()
    return len(params)
