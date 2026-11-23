from __future__ import annotations

from datetime import date, timedelta
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
    is_in_target_area,
    is_likely_non_disabled_staff_job,
    make_http_client,
    polite_sleep,
)

LIST_URL = "https://job.alio.go.kr/recruit.do"


def collect(limit: int = 50) -> List[RawJob]:
    results: List[RawJob] = []
    seen_ids: set[str] = set()
    today = date.today()
    s_date = (today - timedelta(days=92)).strftime("%Y.%m.%d")
    e_date = today.strftime("%Y.%m.%d")

    with make_http_client() as client:
        # ing=2(진행중) + ing=3(마감, 지난 3개월) 모두 수집
        for ing_code in ("2", "3"):
            for page in range(1, 8):
                if len(results) >= limit:
                    break
                resp = client.get(
                    LIST_URL,
                    params={
                        "s_type": "all",
                        "search_word": "장애인",
                        "s_date": s_date,
                        "e_date": e_date,
                        "ing": ing_code,
                        "pageNo": str(page),
                    },
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "lxml")

                found_on_page = 0
                for tr in soup.select("table tbody tr"):
                    if len(results) >= limit:
                        break
                    a = tr.find("a", href=re.compile(r"recruitview\.do"))
                    if not a:
                        continue
                    found_on_page += 1
                    href = a["href"]
                    m = re.search(r"idx=(\d+)", href)
                    idx = m.group(1) if m else href
                    if idx in seen_ids:
                        continue
                    seen_ids.add(idx)

                    tds = [clean_text(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
                    # [chk, 번호, 제목, 기관명, 근무지, 고용형태, 등록일, 마감일]
                    title = clean_text(a.get_text(" ", strip=True)) or (tds[2] if len(tds) > 2 else "")
                    company = tds[3] if len(tds) > 3 else ""
                    location_raw = tds[4] if len(tds) > 4 else ""
                    emp_raw = tds[5] if len(tds) > 5 else ""
                    posted_raw = tds[6] if len(tds) > 6 else ""
                    deadline_raw = tds[7] if len(tds) > 7 else ""

                    if not is_in_target_area(location_raw, title) or is_excluded_role(title):
                        continue
                    if is_likely_non_disabled_staff_job(title):
                        continue

                    detail_url = urljoin("https://job.alio.go.kr/", href)
                    raw_text = f"기관명: {company}\n제목: {title}\n근무지: {location_raw}\n고용형태: {emp_raw}\n마감: {deadline_raw}"
                    attachments: List[dict] = []
                    att_read = False
                    try:
                        polite_sleep(0.25)
                        dr = client.get(detail_url)
                        if dr.status_code == 200:
                            raw_text = extract_readable_text(dr.text, max_chars=2500)
                            attachments, att_txt = collect_and_read_attachments(
                                client, dr.text, detail_url, max_read=2, max_total_chars=3000
                            )
                            if att_txt:
                                raw_text = f"{raw_text}\n\n{att_txt}"
                                att_read = True
                    except Exception:
                        pass

                    if is_likely_non_disabled_staff_job(title, raw_text):
                        continue

                    status_tag = "진행중" if ing_code == "2" else "마감공고"
                    raw_text = f"[잡알리오 공공기관 공고 ({status_tag})]\n{raw_text}"
                    results.append(
                        RawJob(
                            source_id="alio",
                            source_name="잡알리오",
                            external_id=idx,
                            title=title,
                            company=company,
                            location_raw=location_raw,
                            employment_raw=emp_raw,
                            deadline_raw=deadline_raw,
                            posted_raw=posted_raw,
                            url=detail_url,
                            raw_text=raw_text,
                            attachments=attachments,
                            attachment_read=att_read,
                        )
                    )

                if found_on_page == 0:
                    break

    return results
