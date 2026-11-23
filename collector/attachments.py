from __future__ import annotations

import io
import re
import struct
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
import zlib
from typing import List, Tuple
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from collector.base import clean_text

MAX_FILE_BYTES = 8 * 1024 * 1024  # 8MB 제한

DOC_EXTS = (".pdf", ".hwp", ".hwpx", ".docx", ".doc", ".zip")
DOWNLOAD_HINTS = (
    "download.json",
    "nd_filedownload.do",
    "comm/getfile",
    "filedown",
    "filedownload",
    "atchfile",
    "getfile",
)
SKIP_URL_HINTS = (
    "excel",
    "csv",
    "viewer",
    "preview",
    "hwpviewer",
    "acrobat",
    "ezpdf",
    "javascript:",
    "mailto:",
    "tel:",
)
FORM_ONLY_KEYWORDS = (
    "입사지원서",
    "응시원서",
    "지원서",
    "이력서",
    "자기소개서",
    "개인정보",
    "동의서",
    "서식",
    "양식",
    "체크리스트",
    "확인서",
)
NOTICE_PRIORITY_KEYWORDS = (
    "공고",
    "모집",
    "요강",
    "채용",
    "안내",
    "직무기술서",
    "직무설명서",
    "계획",
)


def extract_attachment_links(html: str, base_url: str, max_links: int = 8) -> List[dict]:
    """상세 페이지 HTML에서 실제 첨부파일 다운로드 링크 목록 추출."""
    soup = BeautifulSoup(html, "lxml")
    found: List[dict] = []
    seen_urls: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        href_l = href.lower()
        if any(sk in href_l for sk in SKIP_URL_HINTS):
            continue

        text = clean_text(a.get_text(" ", strip=True))
        title_attr = clean_text(a.get("title") or "")
        label = text or title_attr
        combined_l = f"{href_l} {label.lower()}"

        # PC 프로그램 / 앱 다운로드 등 메뉴 링크 제외
        if any(noise in label.lower() for noise in ("pc 프로그램", "뷰어", "다운로드 안내", "매뉴얼", "앱 다운로드")):
            continue

        is_doc_ext = any(ext in combined_l for ext in DOC_EXTS)
        is_dl_endpoint = any(h in href_l for h in DOWNLOAD_HINTS)

        if not (is_doc_ext or is_dl_endpoint):
            continue

        abs_url = urljoin(base_url, href)
        if abs_url in seen_urls:
            continue
        seen_urls.add(abs_url)

        # 파일명 깔끔하게 정리 (용량 표시 "(74 KB)" 등은 유지하되 불필요 접두/화살표 제거)
        name = re.sub(r"^[▶•·\-\s]+", "", label).strip()
        name = re.sub(r"\s*\(새\s*창\s*열림\)\s*", "", name).strip()
        name = re.sub(r"\s*↗\s*$", "", name).strip()
        if not name or name in ("다운로드", "첨부파일", "원본/첨부 링크", "원본/첨부 링크 열기", "원본/첨부 보기"):
            name = "첨부파일 (공고문/양식)"

        found.append({"name": name[:120], "url": abs_url})
        if len(found) >= max_links:
            break

    return found


def _parse_filename_from_headers(headers: httpx.Headers, fallback_name: str, url: str) -> str:
    cd = headers.get("content-disposition") or ""
    # filename*=UTF-8''...
    m_star = re.search(r"filename\*\s*=\s*(?:UTF-8''|utf-8'')([^;\r\n]+)", cd)
    if m_star:
        try:
            return urllib.parse.unquote(m_star.group(1)).strip(' "\'')
        except Exception:
            pass
    m_plain = re.search(r'filename\s*=\s*"?([^";\r\n]+)"?', cd)
    if m_plain:
        raw_fn = m_plain.group(1).strip(' "\'')
        if "%" in raw_fn:
            try:
                raw_fn = urllib.parse.unquote(raw_fn)
            except Exception:
                pass
        try:
            # EUC-KR / UTF-8 보정 시도
            raw_bytes = raw_fn.encode("latin-1")
            for enc in ("utf-8", "cp949", "euc-kr"):
                try:
                    return raw_bytes.decode(enc)
                except Exception:
                    continue
        except Exception:
            return raw_fn
    if fallback_name and any(ext in fallback_name.lower() for ext in DOC_EXTS):
        return fallback_name
    path = urllib.parse.urlparse(url).path
    if path and "." in path.rsplit("/", 1)[-1]:
        return urllib.parse.unquote(path.rsplit("/", 1)[-1])
    return fallback_name


def _extract_pdf_text(data: bytes, max_chars: int = 3500) -> str:
    try:
        import pymupdf

        parts: List[str] = []
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            for page_idx in range(min(len(doc), 5)):
                txt = doc[page_idx].get_text("text") or ""
                if txt.strip():
                    parts.append(txt)
                if sum(len(p) for p in parts) >= max_chars:
                    break
        return clean_text("\n".join(parts))[:max_chars]
    except Exception:
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            parts = []
            for p in reader.pages[:5]:
                txt = p.extract_text() or ""
                if txt.strip():
                    parts.append(txt)
                if sum(len(x) for x in parts) >= max_chars:
                    break
            return clean_text("\n".join(parts))[:max_chars]
        except Exception:
            return ""


def _extract_hwpx_text(data: bytes, max_chars: int = 3500) -> str:
    try:
        parts: List[str] = []
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            sections = sorted(
                n for n in zf.namelist() if re.match(r"Contents/section\d+\.xml$", n, re.I)
            )
            for sec in sections[:5]:
                xml_bytes = zf.read(sec)
                root = ET.fromstring(xml_bytes)
                for elem in root.iter():
                    tag = elem.tag.rsplit("}", 1)[-1]
                    if tag == "t" and elem.text:
                        parts.append(elem.text)
                if sum(len(p) for p in parts) >= max_chars:
                    break
        return clean_text(" ".join(parts))[:max_chars]
    except Exception:
        return ""


def _extract_docx_text(data: bytes, max_chars: int = 3500) -> str:
    try:
        parts: List[str] = []
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if "word/document.xml" not in zf.namelist():
                return ""
            root = ET.fromstring(zf.read("word/document.xml"))
            for elem in root.iter():
                tag = elem.tag.rsplit("}", 1)[-1]
                if tag == "t" and elem.text:
                    parts.append(elem.text)
                elif tag == "p":
                    parts.append("\n")
        return clean_text("".join(parts))[:max_chars]
    except Exception:
        return ""


def _parse_hwp_section_records(stream_bytes: bytes) -> str:
    """HWP 5.x BodyText/Section* 레코드에서 HWPTAG_PARA_TEXT(tag=67) 텍스트 추출."""
    out: List[str] = []
    pos = 0
    n = len(stream_bytes)
    while pos + 4 <= n:
        header = struct.unpack_from("<I", stream_bytes, pos)[0]
        pos += 4
        tag_id = header & 0x3FF
        size = (header >> 20) & 0xFFF
        if size == 0xFFF:
            if pos + 4 > n:
                break
            size = struct.unpack_from("<I", stream_bytes, pos)[0]
            pos += 4
        if pos + size > n:
            break
        rec = stream_bytes[pos : pos + size]
        pos += size

        if tag_id == 67:  # HWPTAG_PARA_TEXT
            chars: List[str] = []
            i = 0
            rlen = len(rec)
            while i + 2 <= rlen:
                code = struct.unpack_from("<H", rec, i)[0]
                # HWP 제어 문자 처리 (확장 제어문자 16바이트, 인라인 16바이트 등)
                if code in (1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23):
                    i += 16
                    continue
                elif code in (0, 4, 5, 6, 7, 8, 9, 19, 20):
                    if code == 9:
                        chars.append(" ")
                    i += 2
                    continue
                elif code in (10, 13):
                    chars.append("\n")
                    i += 2
                    continue
                elif code >= 32:
                    chars.append(chr(code))
                i += 2
            line = "".join(chars).strip()
            if line:
                out.append(line)
    return "\n".join(out)


def _extract_hwp_text(data: bytes, max_chars: int = 3500) -> str:
    try:
        import olefile

        if not olefile.isOleFile(io.BytesIO(data)):
            return ""
        with olefile.OleFileIO(io.BytesIO(data)) as ole:
            is_compressed = True
            if ole.exists("FileHeader"):
                fh = ole.openstream("FileHeader").read()
                if len(fh) >= 40:
                    flags = struct.unpack_from("<I", fh, 36)[0]
                    is_compressed = bool(flags & 1)

            parts: List[str] = []
            sections = sorted(
                [p for p in ole.listdir() if len(p) == 2 and p[0] == "BodyText" and p[1].startswith("Section")],
                key=lambda x: x[1],
            )
            for sec in sections[:4]:
                raw_sec = ole.openstream(sec).read()
                if is_compressed:
                    try:
                        raw_sec = zlib.decompress(raw_sec, -15)
                    except Exception:
                        try:
                            raw_sec = zlib.decompress(raw_sec)
                        except Exception:
                            continue
                txt = _parse_hwp_section_records(raw_sec)
                if txt:
                    parts.append(txt)
                if sum(len(p) for p in parts) >= max_chars:
                    break

            if parts:
                return clean_text("\n".join(parts))[:max_chars]

            # 폴백: PrvText 미리보기 스트림
            if ole.exists("PrvText"):
                prv = ole.openstream("PrvText").read().decode("utf-16le", errors="ignore")
                return clean_text(prv)[:max_chars]
        return ""
    except Exception:
        return ""


def extract_text_from_bytes(data: bytes, filename: str = "", content_type: str = "", max_chars: int = 3500) -> str:
    if not data or len(data) < 32:
        return ""
    fn_l = (filename or "").lower()
    ct_l = (content_type or "").lower()

    # 1) PDF
    if data[:4] == b"%PDF" or fn_l.endswith(".pdf") or "pdf" in ct_l:
        return _extract_pdf_text(data, max_chars=max_chars)

    # 2) OLE HWP (.hwp)
    if data[:4] == b"\xd0\xcf\x11\xe0" or fn_l.endswith(".hwp"):
        return _extract_hwp_text(data, max_chars=max_chars)

    # 3) ZIP 기반 (HWPX / DOCX / 일반 압축 ZIP 안의 공고문)
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()
                if any(re.match(r"Contents/section\d+\.xml$", n, re.I) for n in names):
                    return _extract_hwpx_text(data, max_chars=max_chars)
                if "word/document.xml" in names:
                    return _extract_docx_text(data, max_chars=max_chars)
                # 일반 ZIP이면 내부에서 공고문 PDF/HWP/HWPX 찾아 추출
                candidates = [n for n in names if n.lower().endswith((".pdf", ".hwp", ".hwpx", ".docx"))]
                candidates.sort(key=lambda n: (0 if any(k in n for k in NOTICE_PRIORITY_KEYWORDS) else 1, len(n)))
                for inner in candidates[:2]:
                    inner_bytes = zf.read(inner)
                    txt = extract_text_from_bytes(inner_bytes, filename=inner, max_chars=max_chars)
                    if len(txt) >= 80:
                        return txt
        except Exception:
            return ""

    return ""


def _score_attachment_for_reading(name: str) -> int:
    """공고문/요강 파일은 높은 점수(+), 빈 입사지원서 양식은 낮은 점수(-)."""
    n = (name or "").lower()
    score = 0
    if any(k in n for k in NOTICE_PRIORITY_KEYWORDS):
        score += 10
    if any(k in n for k in FORM_ONLY_KEYWORDS):
        score -= 8
    if ".pdf" in n:
        score += 3
    elif ".hwpx" in n or ".hwp" in n:
        score += 2
    return score


def collect_and_read_attachments(
    client: httpx.Client,
    html: str,
    base_url: str,
    max_read: int = 2,
    max_total_chars: int = 3200,
) -> Tuple[List[dict], str]:
    """
    상세 페이지 HTML에서 첨부파일 링크 목록을 뽑고,
    우선순위 높은 공고문(PDF/HWP/HWPX/DOCX) 최대 max_read개의 본문 텍스트를 추출합니다.
    반환: (attachments_list, combined_extracted_text)
    """
    links = extract_attachment_links(html, base_url)
    if not links:
        return [], ""

    # 읽기 우선순위 정렬 (공고문 우선, 빈 양식 제외)
    indexed = sorted(
        enumerate(links),
        key=lambda pair: _score_attachment_for_reading(pair[1]["name"]),
        reverse=True,
    )

    extracted_blocks: List[str] = []
    read_cnt = 0

    for orig_idx, att in indexed:
        if read_cnt >= max_read:
            break
        score = _score_attachment_for_reading(att["name"])
        # 명확히 입사지원서/동의서 양식만 있는 경우는 스킵 (공고문이 따로 있을 때)
        if score < 0 and read_cnt > 0:
            continue
        if score <= -8 and any(k in att["name"] for k in ("동의서", "이력서", "서식", "양식")) and "공고" not in att["name"]:
            continue

        try:
            resp = client.get(
                att["url"],
                headers={"Referer": base_url},
                timeout=12.0,
            )
            if resp.status_code != 200:
                continue
            ct = (resp.headers.get("content-type") or "").lower()
            if "text/html" in ct:
                continue
            data = resp.content
            if not data or len(data) > MAX_FILE_BYTES:
                continue

            real_name = _parse_filename_from_headers(resp.headers, att["name"], att["url"])
            if real_name and (att["name"].startswith("첨부파일") or len(real_name) > len(att["name"])):
                links[orig_idx]["name"] = real_name[:120]

            txt = extract_text_from_bytes(
                data,
                filename=real_name or att["name"],
                content_type=ct,
                max_chars=max_total_chars,
            )
            if len(txt) >= 60:
                extracted_blocks.append(f"[첨부 공고문: {links[orig_idx]['name']}]\n{txt}")
                read_cnt += 1
        except Exception:
            continue

    combined = "\n\n".join(extracted_blocks)[:max_total_chars]
    return links, combined
