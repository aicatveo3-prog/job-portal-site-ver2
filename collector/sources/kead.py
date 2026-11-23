from __future__ import annotations

from datetime import date, timedelta
import re
from typing import List
from bs4 import BeautifulSoup

from collector.attachments import collect_and_read_attachments
from collector.base import (
    RawJob,
    clean_text,
    extract_readable_text,
    is_excluded_role,
    is_in_target_area,
    make_http_client,
    polite_sleep,
)

LIST_URL = "https://www.kead.or.kr/bbs/jobinfo/bbsPage.do"
DETAIL_URL = "https://www.kead.or.kr/bbs/jobinfo/bbsView.do"


def collect(limit: int = 50) -> List[RawJob]:
    results: List[RawJob] = []
    seen_ids: set[str] = set()
    cutoff_str = (date.today() - timedelta(days=95)).strftime("%Y-%m-%d")

    with make_http_client() as client:
        # 최근 3개월(마감 포함) 딥스캔 (최대 30페이지)
        for page in range(1, 31):
            if len(results) >= limit:
                break
            resp = client.get(LIST_URL, params={"menuId": "MENU2201", "pageIndex": str(page)})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            rows = soup.select("table tbody tr")
            if not rows:
                break

            older_than_cutoff = 0
            for tr in rows:
                if len(results) >= limit:
                    break
                tds = [clean_text(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
                if len(tds) < 6:
                    continue
                posted_raw = tds[6] if len(tds) > 6 else ""
                if re.match(r"^20\d{2}-\d{2}-\d{2}$", posted_raw) and posted_raw < cutoff_str:
                    older_than_cutoff += 1
                    continue
                a = tr.find("a")
                if not a:
                    continue
                onclick = a.get("onclick") or ""
                m = re.search(r"fn_bbsView\(['\"]?(\d+)['\"]?\)", onclick)
                if not m:
                    continue
                bbs_id = m.group(1)
                if bbs_id in seen_ids:
                    continue
                seen_ids.add(bbs_id)

                title = clean_text(a.get_text(" ", strip=True))
                sido = tds[2] if len(tds) > 2 else ""
                sigungu = tds[3] if len(tds) > 3 else ""
                category = tds[4] if len(tds) > 4 else ""
                deadline_raw = tds[5] if len(tds) > 5 else ""
                posted_raw = tds[6] if len(tds) > 6 else ""
                location_raw = clean_text(f"{sido} {sigungu}")

                if not is_in_target_area(location_raw, title) or is_excluded_role(title):
                    continue

                view_url = f"{DETAIL_URL}?bbsCnId={bbs_id}&menuId=MENU2201"
                raw_text = f"제목: {title}\n지역: {location_raw}\n구분: {category}\n마감일: {deadline_raw}"
                attachments: List[dict] = []
                att_read = False
                try:
                    polite_sleep(0.3)
                    dr = client.post(
                        DETAIL_URL,
                        data={"bbsCnId": bbs_id, "menuId": "MENU2201"},
                        headers={"Referer": f"{LIST_URL}?menuId=MENU2201"},
                    )
                    if dr.status_code == 200:
                        raw_text = extract_readable_text(dr.text, max_chars=2600)
                        attachments, att_txt = collect_and_read_attachments(
                            client, dr.text, view_url, max_read=1, max_total_chars=2800
                        )
                        if att_txt:
                            raw_text = f"{raw_text}\n\n{att_txt}"
                            att_read = True
                except Exception:
                    pass

                # 기업명 힌트 추출 ([지사명] 제거)
                company_hint = re.sub(r"^\[[^\]]+\]\s*", "", title)
                company_hint = company_hint.split()[0] if company_hint.split() else "한국장애인고용공단 안내기업"

                results.append(
                    RawJob(
                        source_id="kead",
                        source_name="한국장애인고용공단",
                        external_id=bbs_id,
                        title=title,
                        company=company_hint,
                        location_raw=location_raw,
                        employment_raw=category,
                        deadline_raw=deadline_raw,
                        posted_raw=posted_raw,
                        url=view_url,
                        raw_text=raw_text,
                        attachments=attachments,
                        attachment_read=att_read,
                    )
                )
            if older_than_cutoff >= len(rows):
                break

    return results
