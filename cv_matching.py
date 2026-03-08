"""
Install:
  pip install -U sentence-transformers torch numpy

Run:
  python match_score.py
"""

from __future__ import annotations
import re
import json
from typing import Dict, Any, List, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer, util


def normalize_skill(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9\+\#\.\s-]", " ", s)  # keep node.js, c++, c#
    s = re.sub(r"\s+", " ", s).strip()
    return s


def clamp01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


def experience_score(candidate_years: float, job_years: float) -> float:
    """
    Rules:
    - If job experience is None → score = 0.0
    - Otherwise → min(candidate / job, 1)
    """

    # ✅ If job does NOT require experience
    if job_years is None:
        return None

    try:
        c = float(candidate_years or 0.0)
    except ValueError:
        c = 0.0

    try:
        j = float(job_years)
    except ValueError:
        return 1.0

    if j <= 0:
        return 0.0

    return min(c / j, 1.0)


class SimilaritySkillMatcher:
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        similarity_threshold: float = 0.60,
    ):
        self.model = SentenceTransformer(model_name)
        self.threshold = float(similarity_threshold)

    def skills_score(
        self,
        candidate_payload: Dict[str, Any],
        job_payload: Dict[str, Any],
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Skills rate rule:
          total_skills_rate = verified_matched * 1 + unverified_matched * 0.5

        Matching rule:
          For each JOB skill, find best matching candidate skill by cosine similarity.
          If best similarity >= threshold => matched.

        Normalization:
          skills_score = total_skills_rate / (number_of_job_skills * 1.0)
          (Best case: all job skills matched with verified candidate skills)
        """
        cand_items = candidate_payload.get("skills", []) or []
        job_items = job_payload.get("skills", []) or []

        candidate_skills = []
        candidate_verified = []
        for s in cand_items:
            name = normalize_skill(s.get("skillName", ""))
            if name:
                candidate_skills.append(name)
                candidate_verified.append(bool(s.get("verified", False)))

        job_skills = []
        for s in job_items:
            name = normalize_skill(s.get("skillName", ""))
            if name:
                job_skills.append(name)

        if not job_skills or not candidate_skills:
            return 0.0, []

        cand_emb = self.model.encode(candidate_skills, convert_to_tensor=True, normalize_embeddings=True)
        job_emb = self.model.encode(job_skills, convert_to_tensor=True, normalize_embeddings=True)

        # (num_job x num_candidate)
        sims = util.cos_sim(job_emb, cand_emb).cpu().numpy()

        total_rate = 0.0
        details: List[Dict[str, Any]] = []

        for j, job_skill in enumerate(job_skills):
            best_i = int(np.argmax(sims[j]))
            best_sim = float(sims[j][best_i])
            best_cand_skill = candidate_skills[best_i]
            best_verified = candidate_verified[best_i]

            matched = best_sim >= self.threshold
            if matched:
                total_rate += 1.0 if best_verified else 0.5

            details.append({
                "job_skill": job_skill,
                "best_candidate_skill": best_cand_skill,
                "similarity": round(best_sim, 4),
                "matched": matched,
                "candidate_verified_used": best_verified
            })

        max_possible = len(job_skills) * 1.0
        skills_score = clamp01(total_rate / max_possible)

        return skills_score, details

    def final_score(
        self,
        candidate_payload: Dict[str, Any],
        job_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        exp_score = experience_score(
            candidate_payload.get("totalExperience", 0),
            job_payload.get("totalExperience", None),
        )

        s_score, matches = self.skills_score(candidate_payload, job_payload)
        if exp_score == None:
            final = s_score
        else:
            final = max((0.7 * exp_score ),0.4)+ 0.3 * s_score

        return {
            "experience_score": exp_score,
            "final_score": clamp01(final),
            "skills_score": s_score,
            "matches": matches,
        }


if __name__ == "__main__":
    # Candidate payload (can include verified)
    candidate = {
        "totalExperience": 0.0,
        "skills": [
            {"skillName": "Node", "verified": True},
            {"skillName": "Express.js", "verified": False},
            {"skillName": "Mongo DB", "verified": True},
            {"skillName": "JavaScript", "verified": True},
        ]
    }

    # Job payload (no verified needed)
    job = {
        "totalExperience": 4.0,
        "skills": [
            {"skillName": "Node.js"},
            {"skillName": "MongoDB"},
            {"skillName": "express"}
        ]
    }

    # scraped jobs
    job2 = {
        "skills": [
            {"skillName": "Node.js"},
            {"skillName": "MongoDB"},
            {"skillName": "express"},
            {"skillName": "JS"}
        ]
    }

    matcher = SimilaritySkillMatcher(similarity_threshold=0.60)
    result = matcher.final_score(candidate, job)
    print(json.dumps(result, indent=2))