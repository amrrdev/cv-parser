from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from typing import Any, Dict, Optional

from dotenv import load_dotenv
import httpx
from fastapi import APIRouter, BackgroundTasks, FastAPI, HTTPException, status
from pydantic import BaseModel

from cv_matching import SimilaritySkillMatcher
from matching_db import (
    fetch_active_candidate_rows,
    fetch_direct_job_rows,
    fetch_scraped_job_rows,
    get_connection,
    upsert_direct_matches,
    upsert_scraped_matches,
)
from matching_payloads import (
    build_candidate_payloads,
    build_direct_job_payload,
    build_scraped_job_payloads,
)


load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

matching_router = APIRouter(tags=["matching"])


class DirectJobMatchRequest(BaseModel):
    jobId: str
    requestId: Optional[str] = None


class ScrapedJobsMatchRequest(BaseModel):
    since: datetime
    until: datetime
    requestId: Optional[str] = None


class MatchRunResponse(BaseModel):
    type: str
    status: str
    requestId: Optional[str] = None
    jobId: Optional[str] = None
    since: Optional[str] = None
    until: Optional[str] = None
    processedJobs: int
    processedCandidates: int
    upsertedMatches: int
    startedAt: str
    finishedAt: str
    callbackDelivered: bool = False
    callbackError: Optional[str] = None


class AcceptedMatchResponse(BaseModel):
    type: str
    status: str
    requestId: str
    jobId: Optional[str] = None
    since: Optional[str] = None
    until: Optional[str] = None
    acceptedAt: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def get_match_score_scale() -> Decimal:
    raw_value = os.getenv("MATCH_SCORE_SCALE", "100")
    return Decimal(str(raw_value))


def scale_match_score(score: float) -> Decimal:
    scaled = Decimal(str(score)) * get_match_score_scale()
    return scaled.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ensure_request_id(request_id: Optional[str]) -> str:
    return request_id or str(uuid.uuid4())


def get_callback_target(match_type: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    callback_config = {
        "direct": (
            os.getenv("MATCHING_DIRECT_CALLBACK_URL"),
            os.getenv("MATCHING_DIRECT_CALLBACK_TOKEN") or os.getenv("MATCHING_CALLBACK_TOKEN"),
            "MATCHING_DIRECT_CALLBACK_URL",
        ),
        "scraped": (
            os.getenv("MATCHING_SCRAPED_CALLBACK_URL"),
            os.getenv("MATCHING_SCRAPED_CALLBACK_TOKEN") or os.getenv("MATCHING_CALLBACK_TOKEN"),
            "MATCHING_SCRAPED_CALLBACK_URL",
        ),
    }
    return callback_config.get(match_type, (None, None, None))


@lru_cache(maxsize=1)
def get_matcher() -> SimilaritySkillMatcher:
    model_name = os.getenv("MATCHING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
    threshold = float(os.getenv("MATCHING_SIMILARITY_THRESHOLD", "0.60"))
    local_files_only = os.getenv("MATCHING_LOCAL_FILES_ONLY", "false").lower() == "true"
    logger.info(
        "Loading matcher model '%s' with threshold %.2f (local_files_only=%s)",
        model_name,
        threshold,
        local_files_only,
    )
    return SimilaritySkillMatcher(
        model_name=model_name,
        similarity_threshold=threshold,
        local_files_only=local_files_only,
    )


def send_callback(match_type: str, payload: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    callback_url, callback_token, missing_env_name = get_callback_target(match_type)
    if not callback_url:
        return False, f"{missing_env_name} is not configured"

    headers = {}
    if callback_token:
        headers["Authorization"] = f"Bearer {callback_token}"

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(callback_url, json=payload, headers=headers)
            response.raise_for_status()
        return True, None
    except Exception as exc:
        logger.warning("Matching callback failed: %s", exc)
        return False, str(exc)


def build_success_response(
    match_type: str,
    started_at: datetime,
    finished_at: datetime,
    request_id: Optional[str],
    processed_jobs: int,
    processed_candidates: int,
    upserted_matches: int,
    job_id: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> MatchRunResponse:
    response = MatchRunResponse(
        type=match_type,
        status="completed",
        requestId=request_id,
        jobId=job_id,
        since=to_iso(since) if since else None,
        until=to_iso(until) if until else None,
        processedJobs=processed_jobs,
        processedCandidates=processed_candidates,
        upsertedMatches=upserted_matches,
        startedAt=to_iso(started_at),
        finishedAt=to_iso(finished_at),
    )
    callback_delivered, callback_error = send_callback(match_type, response.model_dump(exclude_none=True))
    response.callbackDelivered = callback_delivered
    response.callbackError = callback_error
    return response


def send_failure_callback(
    match_type: str,
    started_at: datetime,
    request_id: Optional[str],
    error_message: str,
    job_id: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> None:
    payload = {
        "type": match_type,
        "status": "failed",
        "requestId": request_id,
        "jobId": job_id,
        "since": to_iso(since) if since else None,
        "until": to_iso(until) if until else None,
        "error": error_message,
        "startedAt": to_iso(started_at),
        "finishedAt": to_iso(utc_now()),
    }
    send_callback(match_type, {key: value for key, value in payload.items() if value is not None})


def run_direct_job_matching(request: DirectJobMatchRequest) -> MatchRunResponse:
    started_at = utc_now()

    with get_connection() as connection:
        candidate_rows = fetch_active_candidate_rows(connection)
        direct_job_rows = fetch_direct_job_rows(connection, request.jobId)

        if not direct_job_rows:
            raise HTTPException(status_code=404, detail="Direct job not found or not published")

        candidate_payloads = build_candidate_payloads(candidate_rows)
        job_payload = build_direct_job_payload(direct_job_rows)
        matcher = get_matcher()

        upsert_rows = []
        for job_seeker_id, candidate_payload in candidate_payloads.items():
            result = matcher.final_score(candidate_payload, job_payload)
            upsert_rows.append(
                {
                    "direct_job_id": request.jobId,
                    "job_seeker_id": job_seeker_id,
                    "match_score": scale_match_score(result["final_score"]),
                }
            )

        upserted_matches = upsert_direct_matches(connection, upsert_rows)

    return build_success_response(
        match_type="direct",
        started_at=started_at,
        finished_at=utc_now(),
        request_id=request.requestId,
        processed_jobs=1,
        processed_candidates=len(candidate_payloads),
        upserted_matches=upserted_matches,
        job_id=request.jobId,
    )


def run_scraped_jobs_matching(request: ScrapedJobsMatchRequest) -> MatchRunResponse:
    started_at = utc_now()

    with get_connection() as connection:
        candidate_rows = fetch_active_candidate_rows(connection)
        scraped_job_rows = fetch_scraped_job_rows(connection, request.since, request.until)

        candidate_payloads = build_candidate_payloads(candidate_rows)
        scraped_job_payloads = build_scraped_job_payloads(scraped_job_rows)
        matcher = get_matcher()

        upsert_rows = []
        for job_id, job_payload in scraped_job_payloads.items():
            for job_seeker_id, candidate_payload in candidate_payloads.items():
                result = matcher.final_score(candidate_payload, job_payload)
                upsert_rows.append(
                    {
                        "scraped_job_id": job_id,
                        "job_seeker_id": job_seeker_id,
                        "match_score": scale_match_score(result["final_score"]),
                    }
                )

        upserted_matches = upsert_scraped_matches(connection, upsert_rows)

    return build_success_response(
        match_type="scraped",
        started_at=started_at,
        finished_at=utc_now(),
        request_id=request.requestId,
        processed_jobs=len(scraped_job_payloads),
        processed_candidates=len(candidate_payloads),
        upserted_matches=upserted_matches,
        since=request.since,
        until=request.until,
    )


def execute_direct_job_matching(request: DirectJobMatchRequest) -> None:
    started_at = utc_now()
    logger.info(
        "Started async direct job matching requestId=%s jobId=%s",
        request.requestId,
        request.jobId,
    )
    try:
        result = run_direct_job_matching(request)
        logger.info(
            "Completed async direct job matching requestId=%s upsertedMatches=%s",
            request.requestId,
            result.upsertedMatches,
        )
    except HTTPException as exc:
        send_failure_callback("direct", started_at, request.requestId, str(exc.detail), job_id=request.jobId)
        logger.warning(
            "Async direct job matching failed requestId=%s detail=%s",
            request.requestId,
            exc.detail,
        )
    except Exception as exc:
        logger.error("Direct job matching failed: %s", exc, exc_info=True)
        send_failure_callback("direct", started_at, request.requestId, str(exc), job_id=request.jobId)


def execute_scraped_jobs_matching(request: ScrapedJobsMatchRequest) -> None:
    started_at = utc_now()
    logger.info(
        "Started async scraped jobs matching requestId=%s since=%s until=%s",
        request.requestId,
        request.since,
        request.until,
    )
    try:
        result = run_scraped_jobs_matching(request)
        logger.info(
            "Completed async scraped jobs matching requestId=%s upsertedMatches=%s",
            request.requestId,
            result.upsertedMatches,
        )
    except HTTPException as exc:
        send_failure_callback("scraped", started_at, request.requestId, str(exc.detail), since=request.since, until=request.until)
        logger.warning(
            "Async scraped jobs matching failed requestId=%s detail=%s",
            request.requestId,
            exc.detail,
        )
    except Exception as exc:
        logger.error("Scraped jobs matching failed: %s", exc, exc_info=True)
        send_failure_callback("scraped", started_at, request.requestId, str(exc), since=request.since, until=request.until)


@matching_router.post(
    "/match/direct-job",
    response_model=AcceptedMatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def match_direct_job(
    request: DirectJobMatchRequest,
    background_tasks: BackgroundTasks,
) -> AcceptedMatchResponse:
    accepted_at = utc_now()
    request_with_id = request.model_copy(update={"requestId": ensure_request_id(request.requestId)})
    logger.info(
        "Accepted direct job matching requestId=%s jobId=%s",
        request_with_id.requestId,
        request_with_id.jobId,
    )
    background_tasks.add_task(execute_direct_job_matching, request_with_id)
    return AcceptedMatchResponse(
        type="direct",
        status="accepted",
        requestId=request_with_id.requestId,
        jobId=request_with_id.jobId,
        acceptedAt=to_iso(accepted_at),
    )


@matching_router.post(
    "/match/scraped-jobs",
    response_model=AcceptedMatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def match_scraped_jobs(
    request: ScrapedJobsMatchRequest,
    background_tasks: BackgroundTasks,
) -> AcceptedMatchResponse:
    if request.since >= request.until:
        raise HTTPException(status_code=400, detail="'since' must be earlier than 'until'")
    accepted_at = utc_now()
    request_with_id = request.model_copy(update={"requestId": ensure_request_id(request.requestId)})
    logger.info(
        "Accepted scraped jobs matching requestId=%s since=%s until=%s",
        request_with_id.requestId,
        request_with_id.since,
        request_with_id.until,
    )
    background_tasks.add_task(execute_scraped_jobs_matching, request_with_id)
    return AcceptedMatchResponse(
        type="scraped",
        status="accepted",
        requestId=request_with_id.requestId,
        since=to_iso(request_with_id.since),
        until=to_iso(request_with_id.until),
        acceptedAt=to_iso(accepted_at),
    )


if __name__ == "__main__":
    import uvicorn

    app = FastAPI(title="CV Matching Service", version="1.0.0")
    app.include_router(matching_router)

    @app.get("/")
    def root() -> Dict[str, str]:
        return {"message": "CV Matching Service", "version": "1.0.0"}

    @app.get("/health")
    def health_check() -> Dict[str, str]:
        return {"status": "healthy", "timestamp": to_iso(utc_now())}

    uvicorn.run(app, host="0.0.0.0", port=8001)
