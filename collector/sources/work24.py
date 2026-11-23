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
    make_http_client,
    polite_sleep,
)

LIST_URL = "https://www.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do"


def collect(limit: int = 25) -> List[RawJob]:
    results: List[RawJob] = []
    seen_ids: set[str] = set()

    # 1순위: 고양시(41280) 장애인만/병행 채용 (다중 페이지)
    # 2순위: 경기(41000) + 서울(11000) 장애인만(D) 및 병행(Y) 채용 (다중 페이지)
    queries = [
        {"disableEmpHopeGbn": "D", "disableEmpHopeGbnParam": "D", "region": "41280", "resultCnt": "50", "pageIndex": "1"},
        {"disableEmpHopeGbn": "Y", "disableEmpHopeGbnParam": "Y", "region": "41280", "resultCnt": "50", "pageIndex": "1"},
        {"disableEmpHopeGbn": "Y", "disableEmpHopeGbnParam": "Y", "region": "41280", "resultCnt": "50", "pageIndex": "2"},
        {"disableEmpHopeGbn": "D", "disableEmpHopeGbnParam": "D", "region": "41000|11000", "resultCnt": "50", "pageIndex": "1"},
        {"disableEmpHopeGbn": "D", "disableEmpHopeGbnParam": "D", "region": "41000|11000", "resultCnt": "50", "pageIndex": "2"},
        {"disableEmpHopeGbn": "D", "disableEmpHopeGbnParam": "D", "region": "41000|11000", "resultCnt": "50", "pageIndex": "3"},
        {"disableEmpHopeGbn": "D", "disableEmpHopeGbnParam": "D", "region": "41000|11000", "resultCnt": "50", "pageIndex": "4"},
        {"disableEmpHopeGbn": "Y", "disableEmpHopeGbnParam": "Y", "region": "41000|11000", "resultCnt": "50", "pageIndex": "1"},
    ]

    with make_http_client() as client:
        for q in queries:
            if len(results) >= limit:
                break
            try:
                resp = client.get(LIST_URL, params=q)
                resp.raise_for_status()
            except Exception:
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            links = soup.find_all("a", href=re.compile(r"empDetailAuthView\.do"))
            for a in links:
                if len(results) >= limit:
                    break
                href = a["href"]
                m = re.search(r"wantedAuthNo=([^&]+)", href)
                if not m:
                    continue
                wanted_no = m.group(1).strip()
                if wanted_no in seen_ids:
                    continue
                seen_ids.add(wanted_no)

                title = clean_text(a.get_text(" ", strip=True))
                if not title or len(title) < 2 or is_excluded_role(title):
                    continue

                tr = a.find_parent("tr")
                row_txt = clean_text(tr.get_text(" ", strip=True)) if tr else title

                # 기업명 / 급여 / 지역 / 마감 힌트 추출
                company = ""
                if tr:
                    first_td = tr.find("td")
                    if first_td:
                        c_node = first_td.select_one("a, strong, span, p")
                        company = clean_text(c_node.get_text(" ", strip=True)) if c_node else ""
                if not company or company == title:
                    company = row_txt.split(title)[0].strip()[:40] if title in row_txt else ""

                sal_m = re.search(r"(?:시급|월급|연봉|일급)\s*[\d,]+\s*원(?:\s*~\s*[\d,]+\s*원)?", row_txt)
                salary_raw = sal_m.group(0) if sal_m else ""
                loc_m = re.search(r"(?:경기도|서울특별시|서울|경기)\s+[가-힣]+(?:시|구|군)(?:\s+[가-힣0-9]+)?", row_txt)
                location_raw = loc_m.group(0) if loc_m else ""
                dl_m = re.search(r"마감일\s*:\s*([0-9\-채용시까지]+)", row_txt)
                deadline_raw = dl_m.group(1) if dl_m else ""

                detail_url = urljoin("https://www.work24.go.kr", href)
                raw_text = row_txt
                try:
                    polite_sleep(0.4)
                    dr = client.get(detail_url)
                    if dr.status_code == 200:
                        raw_text = extract_readable_text(dr.text, max_chars=4500)
                except Exception:
                    pass

                hope_tag = "장애인만 채용" if q["disableEmpHopeGbn"] == "D" else "장애인 병행채용"
                raw_text = f"[고용24 구분: {hope_tag}]\n{raw_text}"

                results.append(
                    RawJob(
                        source_id="work24",
                        source_name="고용24",
                        external_id=wanted_no,
                        wanted_auth_no=wanted_no,
                        title=title,
                        company=company,
                        location_raw=location_raw,
                        salary_raw=salary_raw,
                        employment_raw=hope_tag,
                        deadline_raw=deadline_raw,
                        url=detail_url,
                        raw_text=raw_text,
                    )
                )

    return results
