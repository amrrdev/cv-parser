from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


EXPERIENCE_LEVEL_TO_YEARS = {
    "ENTRY": 1.0,
    "JUNIOR": 2.0,
    "MID": 4.0,
    "SENIOR": 6.0,
    "LEAD": 8.0,
    "MANAGER": 10.0,
}


def map_experience_level_to_years(experience_level: Optional[str]) -> Optional[float]:
    if not experience_level:
        return None
    return EXPERIENCE_LEVEL_TO_YEARS.get(str(experience_level).upper())


def build_candidate_payloads(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    payloads: Dict[str, Dict[str, Any]] = {}
    seen_skills: Dict[str, set] = {}

    for row in rows:
        job_seeker_id = str(row["job_seeker_id"])
        payload = payloads.setdefault(
            job_seeker_id,
            {
                "totalExperience": float(row.get("years_of_experience") or 0.0),
                "skills": [],
            },
        )

        payload["totalExperience"] = float(row.get("years_of_experience") or 0.0)
        skill_name = row.get("skill_name")
        verified = bool(row.get("verified", False))

        if not skill_name:
            continue

        skill_key = (skill_name, verified)
        seeker_seen = seen_skills.setdefault(job_seeker_id, set())
        if skill_key in seeker_seen:
            continue

        payload["skills"].append(
            {
                "skillName": skill_name,
                "verified": verified,
            }
        )
        seeker_seen.add(skill_key)

    return payloads


def build_direct_job_payload(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        raise ValueError("No direct job rows provided")

    payload = {
        "totalExperience": map_experience_level_to_years(rows[0].get("experience_level")),
        "skills": [],
    }
    seen_skills = set()

    for row in rows:
        skill_name = row.get("skill_name")
        if not skill_name or skill_name in seen_skills:
            continue

        payload["skills"].append({"skillName": skill_name})
        seen_skills.add(skill_name)

    return payload


def build_scraped_job_payloads(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    payloads: Dict[str, Dict[str, Any]] = {}
    seen_skills: Dict[str, set] = {}

    for row in rows:
        job_id = str(row["job_id"])
        payload = payloads.setdefault(
            job_id,
            {
                "totalExperience": None,
                "skills": [],
            },
        )

        skill_name = row.get("skill_name")
        if not skill_name:
            continue

        job_seen = seen_skills.setdefault(job_id, set())
        if skill_name in job_seen:
            continue

        payload["skills"].append({"skillName": skill_name})
        job_seen.add(skill_name)

    return payloads
