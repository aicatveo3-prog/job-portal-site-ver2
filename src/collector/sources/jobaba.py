from __future__ import annotations

import re
from typing import List
from collector.base import (
    RawJob,
    clean_text,
    is_excluded_role,
    is_in_target_area,
    is_likely_non_disabled_staff_job,
    make_http_client,
)

AJAX_URL = "https://job.gg.go.kr/pblcEmpmn/listAjax.do"
REFERER_URL = "https://job.gg.go.kr/pblcEmpmn/list.do"


def collect(limit: int = 25) -> List[RawJob]:
    results: List[RawJob] = []
    seen_ids: set[str] = set()

    with make_http_client() as client:
        for page in range(1, 5):
            if len(results) >= limit:
                break
            resp = client.post(
                AJAX_URL,
                data={
                    "srchTxt": "장애인",
                    "currentPageNo": str(page),
                    "pageIndex": str(page),
                    "recordCountPerPage": "50",
                },
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": REFERER_URL,
                },
            )
            resp.raise_for_status()
            payload = resp.json()

            # JSON 안에서 실제 공고 리스트 키 찾기 (보통 LIST, list, resultList 등)
            items = []
            for k, v in payload.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    if any(it.get("title") or it.get("instNm") for it in v):
                        items = v
                        break
            if not items:
                break

            new_on_page = 0
            for it in items:
                if len(results) >= limit:
                    break
                title = clean_text(str(it.get("title") or ""))
                if not title:
                    continue
                company = clean_text(str(it.get("instNm") or ""))
                seq = str(it.get("seq") or it.get("apiSn") or "")
                if not seq:
                    seq = f"jb_{page}_{len(results)}"
                if seq in seen_ids:
                    continue

                rgn = clean_text(str(it.get("workRgnCdsNm") or ""))
                rgn_dtl = clean_text(str(it.get("workRgnDtlCdsNm") or ""))
                location_raw = clean_text(f"{rgn} {rgn_dtl}") or "경기도"
                if not is_in_target_area(location_raw, title) or is_excluded_role(title):
                    continue

                rcrut_cntnt = clean_text(str(it.get("rcrutCntnt") or ""))
                if is_likely_non_disabled_staff_job(title, rcrut_cntnt):
                    continue

                seen_ids.add(seq)
                new_on_page += 1
                emp_raw = clean_text(str(it.get("empFrCdsNm") or ""))
                field_raw = clean_text(str(it.get("rcrutFldCdsNm") or ""))
                end_dt = clean_text(str(it.get("endDt") or ""))
                bgn_dt = clean_text(str(it.get("bgnDt") or ""))
                dtl_url = clean_text(str(it.get("dtlUrl") or ""))
                if not dtl_url or not dtl_url.startswith("http"):
                    dtl_url = f"https://job.gg.go.kr/pblcEmpmn/list.do?srchTxt=%EC%9E%A5%EC%95%A0%EC%9D%B8#seq={seq}"

                raw_parts = [
                    f"[잡아바 경기도 공공/기관 채용]",
                    f"기관명: {company}",
                    f"공고명: {title}",
                    f"근무지역: {location_raw}",
                    f"고용형태: {emp_raw}",
                    f"모집분야: {field_raw}",
                    f"접수기간: {bgn_dt} ~ {end_dt}",
                ]
                if it.get("rcrutPrsn"):
                    raw_parts.append(f"모집인원: {it.get('rcrutPrsn')}명")
                if rcrut_cntnt:
                    raw_parts.append(f"상세내용:\n{rcrut_cntnt}")

                results.append(
                    RawJob(
                        source_id="jobaba",
                        source_name="잡아바",
                        external_id=seq,
                        title=title,
                        company=company,
                        location_raw=location_raw,
                        employment_raw=emp_raw,
                        deadline_raw=end_dt,
                        posted_raw=bgn_dt,
                        url=dtl_url,
                        raw_text="\n".join(raw_parts)[:4500],
                    )
                )
            if new_on_page == 0:
                break

    return results
