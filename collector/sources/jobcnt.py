from __future__ import annotations

import re
from typing import List
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from collector.attachments import collect_and_read_attachments
from collector.base import (
    RawJob,
    clean_text,
    extract_readable_text,
    is_excluded_role,
    is_likely_non_disabled_staff_job,
    make_http_client,
    polite_sleep,
)

JOB_URL = "https://jobcnt.or.kr/job.php"
DISTRICT_URL = "https://jobcnt.or.kr/district.php"


def collect(limit: int = 25) -> List[RawJob]:
    results: List[RawJob] = []
    seen_urls: set[str] = set()

    with make_http_client() as client:
        # 1. 민간/공공 구인공고 (job.php — 장애인 전용 구인, 마감 포함 최근 3개월 최대 10페이지)
        for page in range(1, 11):
            if len(results) >= limit:
                break
            resp = client.get(JOB_URL, params={"page": str(page)})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            rows = soup.select("table tbody tr")
            if not rows:
                break

            for tr in rows:
                if len(results) >= limit:
                    break
                tds = [clean_text(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
                a = tr.find("a", href=True)
                if not a or len(tds) < 5:
                    continue
                detail_url = urljoin(JOB_URL, a["href"])
                if detail_url in seen_urls:
                    continue
                seen_urls.add(detail_url)

                m = re.search(r"id=(\d+)", detail_url)
                ext_id = f"job_{m.group(1)}" if m else detail_url

                company = tds[0]
                title = tds[1]
                if is_excluded_role(title):
                    continue
                salary_raw = tds[2] if tds[2] != "-" else ""
                emp_raw = tds[3] if tds[3] != "-" else ""
                loc = tds[4] if tds[4] != "-" else ""
                location_raw = f"서울특별시 {loc}" if loc and loc not in ("지역무관", "전국") and "서울" not in loc else (loc or "서울특별시")
                deadline_raw = tds[5] if len(tds) > 5 else ""

                raw_text = f"기관/기업: {company}\n제목: {title}\n급여: {salary_raw}\n고용형태: {emp_raw}\n지역: {location_raw}"
                attachments: List[dict] = []
                att_read = False
                try:
                    polite_sleep(0.3)
                    dr = client.get(detail_url)
                    if dr.status_code == 200:
                        raw_text = extract_readable_text(dr.text, max_chars=2500)
                        attachments, att_txt = collect_and_read_attachments(
                            client, dr.text, detail_url, max_read=1, max_total_chars=2600
                        )
                        if att_txt:
                            raw_text = f"{raw_text}\n\n{att_txt}"
                            att_read = True
                except Exception:
                    pass

                results.append(
                    RawJob(
                        source_id="jobcnt",
                        source_name="서울시장애인일자리센터",
                        external_id=ext_id,
                        title=title,
                        company=company,
                        location_raw=location_raw,
                        salary_raw=salary_raw,
                        employment_raw=emp_raw,
                        deadline_raw=deadline_raw,
                        url=detail_url,
                        raw_text=raw_text,
                        attachments=attachments,
                        attachment_read=att_read,
                    )
                )

        # 2. 자치구 일자리 공고 (district.php) 중 장애인 대상 공고만 선별 (최근 3개월 마감 포함 최대 8페이지)
        for dpage in range(1, 9):
            if len(results) >= limit:
                break
            try:
                dr_list = client.get(DISTRICT_URL, params={"page": str(dpage)})
                if dr_list.status_code != 200:
                    break
                dsoup = BeautifulSoup(dr_list.text, "lxml")
                rows = dsoup.select("table tbody tr")
                if not rows:
                    break
                for tr in rows:
                    if len(results) >= limit:
                        break
                    tds = [clean_text(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
                    a = tr.find("a", href=True)
                    if not a or len(tds) < 5:
                        continue
                    title = tds[1]
                    if "장애인" not in title or is_excluded_role(title):
                        continue
                    if is_likely_non_disabled_staff_job(title):
                        continue
                    detail_url = urljoin(DISTRICT_URL, a["href"])
                    if detail_url in seen_urls:
                        continue
                    seen_urls.add(detail_url)
                    m = re.search(r"id=(\d+)", detail_url)
                    ext_id = f"dist_{m.group(1)}" if m else detail_url

                    raw_text = " ".join(tds)
                    attachments = []
                    att_read = False
                    try:
                        polite_sleep(0.25)
                        dr = client.get(detail_url)
                        if dr.status_code == 200:
                            raw_text = extract_readable_text(dr.text, max_chars=2500)
                            attachments, att_txt = collect_and_read_attachments(
                                client, dr.text, detail_url, max_read=1, max_total_chars=2800
                            )
                            if att_txt:
                                raw_text = f"{raw_text}\n\n{att_txt}"
                                att_read = True
                    except Exception:
                        pass

                    results.append(
                        RawJob(
                            source_id="jobcnt",
                            source_name="서울시장애인일자리센터",
                            external_id=ext_id,
                            title=title,
                            company=tds[0],
                            location_raw=f"서울특별시 {tds[4]}" if tds[4] not in ("-", "지역무관") else "서울특별시",
                            deadline_raw=tds[5] if len(tds) > 5 else "",
                            url=detail_url,
                            raw_text=raw_text,
                            attachments=attachments,
                            attachment_read=att_read,
                        )
                    )
            except Exception:
                break

    return results
