from __future__ import annotations

import re
from typing import List
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from collector.base import (
    RawJob,
    clean_text,
    extract_readable_text,
    is_excluded_role,
    is_in_target_area,
    is_likely_non_disabled_staff_job,
    make_http_client,
    polite_sleep,
)

SEARCH_URL = "https://www.saramin.co.kr/zf_user/search/recruit"
RELAY_DETAIL_URL = "https://www.saramin.co.kr/zf_user/jobs/relay/view-detail"


def collect(limit: int = 25) -> List[RawJob]:
    results: List[RawJob] = []
    seen_ids: set[str] = set()

    # 노이즈를 줄이기 위해 "장애인 전형" / "장애인 채용" / "장애인 재택" / "장애인만 채용" 키워드 다중 페이지 검색
    keywords = ["장애인 전형", "장애인 채용", "장애인 재택", "장애인만 채용", "장애인 제한경쟁"]

    with make_http_client() as client:
        for kw in keywords:
            if len(results) >= limit:
                break
            for page in range(1, 3):
                if len(results) >= limit:
                    break
                try:
                    polite_sleep(0.5)
                    resp = client.get(
                        SEARCH_URL,
                        params={
                            "searchType": "search",
                            "searchword": kw,
                            "recruitPage": str(page),
                            "recruitSort": "reg_dt",
                            "recruitPageCount": "40",
                        },
                    )
                    resp.raise_for_status()
                except Exception:
                    break

                soup = BeautifulSoup(resp.text, "lxml")
                items = soup.select(".item_recruit")
                if not items:
                    break
                for it in items:
                    if len(results) >= limit:
                        break
                    rec_idx = (it.get("value") or "").strip()
                    tit_a = it.select_one(".job_tit a")
                    if not tit_a:
                        continue
                    if not rec_idx:
                        m = re.search(r"rec_idx=(\d+)", tit_a.get("href", ""))
                        rec_idx = m.group(1) if m else ""
                    if not rec_idx or rec_idx in seen_ids:
                        continue

                    title = clean_text(tit_a.get_text(" ", strip=True))
                    corp_a = it.select_one(".corp_name a")
                    company = clean_text(corp_a.get_text(" ", strip=True)) if corp_a else ""

                    cond_spans = [clean_text(sp.get_text(" ", strip=True)) for sp in it.select(".job_condition span")]
                    location_raw = cond_spans[0] if len(cond_spans) > 0 else ""
                    emp_raw = " / ".join(cond_spans[1:]) if len(cond_spans) > 1 else ""
                    date_el = it.select_one(".job_date .date")
                    deadline_raw = clean_text(date_el.get_text(" ", strip=True)) if date_el else ""
                    sector_el = it.select_one(".job_sector")
                    sector_txt = clean_text(sector_el.get_text(" ", strip=True)) if sector_el else ""

                    if not is_in_target_area(location_raw, title) or is_excluded_role(title):
                        continue
                    if is_likely_non_disabled_staff_job(title):
                        continue

                    seen_ids.add(rec_idx)
                    detail_url = urljoin("https://www.saramin.co.kr", tit_a["href"])
                    summary_header = (
                        f"기업명: {company}\n제목: {title}\n근무지: {location_raw}\n"
                        f"조건: {emp_raw}\n직무태그: {sector_txt}\n마감: {deadline_raw}\n"
                    )
                    raw_text = summary_header

                    try:
                        polite_sleep(0.4)
                        dr = client.post(
                            RELAY_DETAIL_URL,
                            data={"rec_idx": rec_idx, "rec_seq": "0"},
                            headers={
                                "Referer": f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={rec_idx}",
                                "X-Requested-With": "XMLHttpRequest",
                            },
                        )
                        if dr.status_code == 200 and len(dr.text) > 150:
                            body_txt = extract_readable_text(dr.text, max_chars=4000)
                            raw_text = f"{summary_header}\n{body_txt}"
                    except Exception:
                        pass

                    if is_likely_non_disabled_staff_job(title, raw_text):
                        continue

                    results.append(
                        RawJob(
                            source_id="saramin",
                            source_name="사람인",
                            external_id=rec_idx,
                            title=title,
                            company=company,
                            location_raw=location_raw,
                            employment_raw=emp_raw,
                            deadline_raw=deadline_raw,
                            url=detail_url,
                            raw_text=raw_text,
                        )
                    )

    return results
