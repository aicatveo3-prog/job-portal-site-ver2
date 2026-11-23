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
    make_http_client,
    polite_sleep,
)

LIST_URL = "https://www.modoojob.com/guin_list.php"


def collect(limit: int = 25) -> List[RawJob]:
    results: List[RawJob] = []
    seen_ids: set[str] = set()

    with make_http_client() as client:
        for page in range(1, 9):
            if len(results) >= limit:
                break
            params = {"pg": str(page)} if page > 1 else {}
            resp = client.get(LIST_URL, params=params)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            links = soup.find_all("a", href=re.compile(r"guin_detail\.php\?num=\d+"))
            if not links:
                break

            for a in links:
                if len(results) >= limit:
                    break
                href = a["href"]
                m = re.search(r"num=(\d+)", href)
                if not m:
                    continue
                num = m.group(1)
                if num in seen_ids:
                    continue

                # 같은 공고에 링크가 여러 개(로고/제목/지역) 있으므로 의미 있는 텍스트가 있는 컨테이너 추출
                container = a.find_parent("tr") or a.find_parent("li") or a.find_parent("div")
                row_txt = clean_text(container.get_text(" ", strip=True)) if container else clean_text(a.get_text(" ", strip=True))
                if len(row_txt) < 6:
                    continue

                seen_ids.add(num)
                detail_url = urljoin("https://www.modoojob.com/", href)

                # 목록 행에서 위치 힌트 먼저 체크 (수도권/재택 외 빠른 스킵)
                loc_m = re.search(r"(?:서울|경기|인천|고양|부산|대구|광주|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주)[^\s·|]{0,12}(?:\s+[가-힣]+(?:구|시|군))?", row_txt)
                location_raw = loc_m.group(0).strip() if loc_m else ""
                if location_raw and not is_in_target_area(location_raw, row_txt):
                    continue
                if is_excluded_role(row_txt):
                    continue

                raw_text = row_txt
                title = ""
                company = ""
                salary_raw = ""
                deadline_raw = ""

                try:
                    polite_sleep(0.35)
                    dr = client.get(detail_url)
                    if dr.status_code == 200:
                        dsoup = BeautifulSoup(dr.text, "lxml")
                        raw_text = extract_readable_text(dr.text, max_chars=4500)
                        # 상세 페이지 <title> 또는 h1/h2에서 제목 추출
                        if dsoup.title and dsoup.title.string:
                            t_str = clean_text(dsoup.title.string)
                            title = re.sub(r"\s*[-|:]\s*모두의잡.*$", "", t_str).strip()
                except Exception:
                    pass

                if not is_in_target_area(location_raw, f"{title} {raw_text[:500]}"):
                    continue

                sal_m = re.search(r"(?:시급|월급|연봉)\s*[\d,]+(?:\s*만원|\s*원)", row_txt)
                if sal_m:
                    salary_raw = sal_m.group(0)
                dl_m = re.search(r"(?:D-\d+|채용시\s*마감|20\d{2}[.\-]\d{1,2}[.\-]\d{1,2})", row_txt)
                if dl_m:
                    deadline_raw = dl_m.group(0)

                if not title:
                    title = row_txt[:70]

                results.append(
                    RawJob(
                        source_id="modoojob",
                        source_name="모두의잡",
                        external_id=num,
                        title=title,
                        company=company,
                        location_raw=location_raw,
                        salary_raw=salary_raw,
                        deadline_raw=deadline_raw,
                        url=detail_url,
                        raw_text=raw_text,
                    )
                )

    return results
