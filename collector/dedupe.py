from __future__ import annotations

import re
from datetime import date
from typing import Dict, List

from collector.base import EnrichedJob


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\(주\)|주식회사|\(사\)|사단법인|\(재\)|재단법인|\[[^\]]+\]", "", s)
    s = re.sub(r"[^0-9a-z가-힣]", "", s)
    return s


def _is_too_old(deadline: str, today: date, keep_expired_days: int = 95) -> bool:
    """마감 후 keep_expired_days(기본 95일 = 약 3개월) 초과한 공고만 제외하고, 지난 3개월 내 마감 공고는 모두 보관."""
    if not deadline or deadline == "채용시까지":
        return False
    m = re.match(r"^(20\d{2})-(\d{2})-(\d{2})$", deadline.strip())
    if not m:
        return False
    try:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return (today - d).days > keep_expired_days
    except ValueError:
        return False


def _is_closed_now(job: EnrichedJob, today: date) -> bool:
    if job.is_closed_in_text:
        return True
    if not job.deadline or job.deadline == "채용시까지":
        return False
    m = re.match(r"^(20\d{2})-(\d{2})-(\d{2})$", job.deadline.strip())
    if not m:
        return False
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) < today
    except ValueError:
        return False


def dedupe_and_sort(jobs: List[EnrichedJob], prev_ids: set[str]) -> List[EnrichedJob]:
    today = date.today()
    merged_map: Dict[str, EnrichedJob] = {}

    for job in jobs:
        if _is_too_old(job.deadline, today):
            continue

        # 1차 키: Work24/고양시 공통 ID 또는 (정규화 기업명 + 정규화 제목 앞 18자)
        if re.match(r"^K[A-Z0-9]{10,}$", job.id):
            dedupe_key = f"auth:{job.id}"
        else:
            dedupe_key = f"ct:{_norm(job.company)[:14]}:{_norm(job.title)[:18]}"

        existing = merged_map.get(dedupe_key)
        if not existing:
            job.is_new = job.id not in prev_ids
            merged_map[dedupe_key] = job
            continue

        # 출처/링크 병합
        for s in job.sources:
            if s not in existing.sources:
                existing.sources.append(s)
        for sid in job.source_ids:
            if sid not in existing.source_ids:
                existing.source_ids.append(sid)
        if job.url != existing.url and job.url not in existing.alt_urls:
            existing.alt_urls.append(job.url)

        # 첨부파일 링크 병합
        seen_att_urls = {a.get("url") for a in existing.attachments if isinstance(a, dict)}
        for a in job.attachments:
            if isinstance(a, dict) and a.get("url") and a["url"] not in seen_att_urls:
                existing.attachments.append(a)
                seen_att_urls.add(a["url"])
        if job.attachment_read:
            existing.attachment_read = True

        # 첨부 공고문까지 AI 분석된 항목 또는 AI 정제된 항목이 더 풍부하므로 우선 채택
        job_better = (job.attachment_read and not existing.attachment_read) or (
            job.ai_processed and not existing.ai_processed
        )
        if job_better:
            job.sources = existing.sources
            job.source_ids = existing.source_ids
            job.attachments = existing.attachments
            job.attachment_read = existing.attachment_read or job.attachment_read
            job.alt_urls = list(dict.fromkeys([existing.url] + existing.alt_urls))
            job.is_new = existing.is_new
            merged_map[dedupe_key] = job
        else:
            # 태그 보강
            for t in job.tags:
                if t not in existing.tags and len(existing.tags) < 7:
                    existing.tags.append(t)

    result = list(merged_map.values())
    # 정렬: 접수중 우선 → 생활권 우선순위(고양시→인접→재택→서울→경기) → 신규 여부 → AI정제 여부 → 월급 높은 순
    result.sort(
        key=lambda j: (
            1 if _is_closed_now(j, today) else 0,
            j.distance_rank,
            0 if j.is_new else 1,
            0 if j.ai_processed else 1,
            -(j.salary_monthly_krw or 0),
        )
    )
    return result
