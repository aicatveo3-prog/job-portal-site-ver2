from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.pipeline import run_pipeline
from notifier.windows_toast import send_toast


def main() -> None:
    parser = argparse.ArgumentParser(description="고양시·수도권·재택 장애인 채용공고 자동 수집기")
    parser.add_argument("--force", action="store_true", help="오늘 이미 실행했더라도 강제로 다시 수집")
    parser.add_argument("--no-ai", action="store_true", help="OpenCode(DeepSeek 4.1) 호출 생략 (규칙 기반 빠른 테스트)")
    parser.add_argument("--limit", type=int, default=None, help="사이트별 최대 수집 건수")
    parser.add_argument("--sources", type=str, default="", help="특정 사이트만 실행 (쉼표 구분, 예: goyang,kead)")
    parser.add_argument("--no-notify", action="store_true", help="윈도우/카톡/메신저 알림 비활성화")
    parser.add_argument("--test-toast", action="store_true", help="윈도우 알림만 테스트")
    args = parser.parse_args()

    if args.test_toast:
        ok = send_toast("장애인 채용공고 알림 테스트", "윈도우 토스트 알림이 정상적으로 작동합니다!")
        print("토스트 전송:", ok)
        return

    only = [s.strip() for s in args.sources.split(",") if s.strip()] if args.sources else None
    use_ai = False if args.no_ai else None

    run_pipeline(
        force=args.force,
        use_ai=use_ai,
        limit_per_source=args.limit,
        only_sources=only,
        notify=not args.no_notify,
    )


if __name__ == "__main__":
    main()
