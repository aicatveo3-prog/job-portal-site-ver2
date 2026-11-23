from __future__ import annotations

import re
from typing import List
from bs4 import BeautifulSoup

from collector.attachments import collect_and_read_attachments
from collector.base import (
    RawJob,
    clean_text,
    extract_readable_text,
    is_excluded_role,
    make_http_client,
    polite_sleep,
)

BASE_LIST_URL = "https://www.goyang.go.kr/jobs/jobInf/BD_selectDisabledEmploymentList.do"
BASE_DETAIL_URL = (
    "https://www.goyang.go.kr/jobs/jobInf/BD_selectDisabledEmployment.do"
    "?page=1&keyword=&occupationList=&regionList=41280,41281,41285,41287"
    "&prefY=Y&prefD=D&pfPreferential=&wantedAuthNo={wanted_no}"
)
PUBLIC_BBS_URL = "https://www.goyang.go.kr/jobs/user/bbs/BD_selectBbsList.do?q_bbsCode=1082"


def collect(limit: int = 25) -> List[RawJob]:
    results: List[RawJob] = []
    seen_ids: set[str] = set()

    with make_http_client() as client:
        # 1. 고양시 장애인 채용 목록 (최대 12페이지 딥스캔)
        for page in range(1, 13):
            if len(results) >= limit:
                break
            resp = client.get(BASE_LIST_URL, params={"q_currPage": str(page)})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            rows = soup.select("table tbody tr")
            if not rows:
                break

            page_found = 0
            for tr in rows:
                if len(results) >= limit:
                    break
                a = tr.find("a", href=True)
                if not a:
                    continue
                m = re.search(r"jsDetail\(['\"]([^'\"]+)['\"]\)", a["href"])
                if not m:
                    continue
                wanted_no = m.group(1).strip()
                if wanted_no in seen_ids:
                    continue
                seen_ids.add(wanted_no)
                page_found += 1

                tds = [clean_text(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
                company = tds[1] if len(tds) > 1 else ""
                title_block = tds[2] if len(tds) > 2 else clean_text(a.get_text(" ", strip=True))
                posted_raw = tds[3] if len(tds) > 3 else ""
                deadline_raw = tds[4] if len(tds) > 4 else ""

                # 제목 영역에서 급여/주소 힌트 추출
                title = clean_text(a.get_text(" ", strip=True)) or title_block
                if is_excluded_role(title, title_block):
                    continue
                sal_m = re.search(r"\((?:월급|시급|연봉|일급)\)\s*[^\s]+(?:\s*[^\s]+)?", title_block)
                salary_raw = sal_m.group(0) if sal_m else ""
                loc_m = re.search(r"경기도\s+고양시[^\d]*?(?=\s*$|\s+\d)", title_block)
                location_raw = loc_m.group(0).strip() if loc_m else "경기도 고양시"

                detail_url = BASE_DETAIL_URL.format(wanted_no=wanted_no)
                raw_text = title_block
                try:
                    polite_sleep(0.35)
                    dr = client.get(detail_url)
                    if dr.status_code == 200:
                        raw_text = extract_readable_text(dr.text, max_chars=4500)
                except Exception:
                    pass

                results.append(
                    RawJob(
                        source_id="goyang",
                        source_name="고양시 일자리망",
                        external_id=wanted_no,
                        wanted_auth_no=wanted_no,
                        title=title,
                        company=company,
                        location_raw=location_raw,
                        salary_raw=salary_raw,
                        deadline_raw=deadline_raw,
                        posted_raw=posted_raw,
                        url=detail_url,
                        raw_text=raw_text,
                    )
                )
            if page_found == 0:
                break

        # 2. 고양시 공공채용 게시판 중 '장애인' 관련 공고 (과거 3개월 마감 포함 최대 10페이지)
        for pub_page in range(1, 11):
            if len(results) >= limit:
                break
            try:
                pr = client.get(PUBLIC_BBS_URL, params={"q_bbsCode": "1082", "q_currPage": str(pub_page)})
                if pr.status_code != 200:
                    break
                psoup = BeautifulSoup(pr.text, "lxml")
                rows = psoup.select("table tbody tr")
                if not rows:
                    break
                for tr in rows:
                    txt = clean_text(tr.get_text(" ", strip=True))
                    if "장애인" not in txt:
                        continue
                    a = tr.find("a")
                    title = clean_text(a.get_text(" ", strip=True)) if a else txt[:80]
                    if is_excluded_role(title, txt):
                        continue
                    onclick = (a.get("onclick") or "") if a else ""
                    href = (a.get("href") or "") if a else ""
                    m = re.search(r"(\d{8,22})", f"{onclick} {href}")
                    bbsctt_sn = m.group(1) if m else f"p{pub_page}_{len(results)}"
                    ext_id = f"pub_{bbsctt_sn}"
                    if ext_id in seen_ids:
                        continue
                    seen_ids.add(ext_id)
                    detail_url = (
                        f"https://www.goyang.go.kr/jobs/user/bbs/BD_selectBbs.do"
                        f"?q_bbsCode=1082&q_bbscttSn={bbsctt_sn}"
                    )
                    raw_text = txt
                    attachments: List[dict] = []
                    att_read = False
                    if m:
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
                    tds = [clean_text(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
                    results.append(
                        RawJob(
                            source_id="goyang",
                            source_name="고양시 일자리망",
                            external_id=ext_id,
                            title=title,
                            company="고양특례시 (공공채용)",
                            location_raw="경기도 고양시",
                            deadline_raw=tds[3] if len(tds) > 3 else "",
                            posted_raw=tds[4] if len(tds) > 4 else "",
                            url=detail_url,
                            raw_text=raw_text,
                            attachments=attachments,
                            attachment_read=att_read,
                        )
                    )
            except Exception:
                break

    return results
