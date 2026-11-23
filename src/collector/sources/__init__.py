from __future__ import annotations

from collector.sources.goyang import collect as collect_goyang
from collector.sources.kead import collect as collect_kead
from collector.sources.work24 import collect as collect_work24
from collector.sources.jobcnt import collect as collect_jobcnt
from collector.sources.alio import collect as collect_alio
from collector.sources.saramin import collect as collect_saramin
from collector.sources.modoojob import collect as collect_modoojob
from collector.sources.jobaba import collect as collect_jobaba

ALL_SOURCES = [
    ("goyang", "고양시 일자리망", collect_goyang),
    ("kead", "한국장애인고용공단", collect_kead),
    ("work24", "고용24", collect_work24),
    ("jobcnt", "서울시장애인일자리센터", collect_jobcnt),
    ("alio", "잡알리오", collect_alio),
    ("saramin", "사람인", collect_saramin),
    ("modoojob", "모두의잡", collect_modoojob),
    ("jobaba", "잡아바", collect_jobaba),
]
