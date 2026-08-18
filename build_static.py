# ============================================================
# build_static.py - data/*.json → docs/data/* 정적 사이트용 변환 스크립트
# 빨모쌤과 함께하는 영어공부 웹앱
#
# GitHub Pages는 정적 파일만 서빙하므로, Flask 앱이 요청마다 만들어주던
# 데이터를 미리 파일로 잘라둔다. sync_notion.py(Notion 파싱 로직)는
# 건드리지 않고, 그 결과물(data/youtube_lessons.json, data/book_units.json)을
# 읽어 변환만 한다.
#
# 사용법:
#   python build_static.py
# ============================================================

import os
import re
import json
import shutil

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
YOUTUBE_JSON  = os.path.join(BASE_DIR, 'data', 'youtube_lessons.json')
BOOK_JSON     = os.path.join(BASE_DIR, 'data', 'book_units.json')

DOCS_DIR       = os.path.join(BASE_DIR, 'docs')
DOCS_DATA_DIR  = os.path.join(DOCS_DIR, 'data')
DOCS_YT_DIR    = os.path.join(DOCS_DATA_DIR, 'youtube')
DOCS_STATIC_DIR = os.path.join(DOCS_DIR, 'static')

SRC_STATIC_DIR = os.path.join(BASE_DIR, 'static')


def strip_html(text):
    """HTML 태그를 제거하고 순수 텍스트만 반환한다 (검색용)."""
    return re.sub(r'<[^>]+>', '', text or '')


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_youtube_data():
    """
    data/youtube_lessons.json을 읽어:
    - docs/data/youtube/<date>.json (날짜별 전체 lesson)
    - docs/data/index.json (홈 화면/검색용 경량 인덱스)
    을 생성한다.
    """
    data = load_json(YOUTUBE_JSON)
    dates = sorted(data.keys(), reverse=True)

    os.makedirs(DOCS_YT_DIR, exist_ok=True)

    index = {}
    for date in dates:
        lesson = data[date]

        # 날짜별 전체 데이터 저장
        with open(os.path.join(DOCS_YT_DIR, f'{date}.json'), 'w', encoding='utf-8') as f:
            json.dump(lesson, f, ensure_ascii=False)

        # 홈 화면용 경량 인덱스 항목 (제목 우선, 키워드 영어 표현도 검색 대상)
        keywords_text = ' '.join(strip_html(s.get('en', '')) for s in lesson.get('keywords', []))
        index[date] = {
            'name':            lesson.get('name', ''),
            'youtube_url':     lesson.get('youtube_url', ''),
            'keywords_count':    len(lesson.get('keywords', [])),
            'my_sentences_count': len(lesson.get('my_sentences', [])),
            'search_title':    (lesson.get('name') or '').lower(),
            'search_keywords': keywords_text.lower(),
        }

    with open(os.path.join(DOCS_DATA_DIR, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump({'dates': dates, 'lessons': index}, f, ensure_ascii=False)

    print(f'[build_static] 유튜브 학습 데이터 {len(dates)}개 날짜 → {DOCS_YT_DIR}')

    # 더 이상 존재하지 않는 날짜의 옛 파일은 정리 (Notion에서 페이지가 삭제된 경우)
    existing_files = {f for f in os.listdir(DOCS_YT_DIR) if f.endswith('.json')}
    expected_files = {f'{d}.json' for d in dates}
    for stale in existing_files - expected_files:
        os.remove(os.path.join(DOCS_YT_DIR, stale))


def build_book_data():
    """data/book_units.json을 docs/data/book_units.json으로 그대로 복사한다."""
    os.makedirs(DOCS_DATA_DIR, exist_ok=True)
    shutil.copyfile(BOOK_JSON, os.path.join(DOCS_DATA_DIR, 'book_units.json'))
    print(f'[build_static] 책 학습 데이터 → {DOCS_DATA_DIR}/book_units.json')


def sync_static_assets():
    """static/css, static/js를 docs/static/으로 그대로 복사해 최신 상태를 유지한다."""
    if os.path.exists(DOCS_STATIC_DIR):
        shutil.rmtree(DOCS_STATIC_DIR)
    shutil.copytree(SRC_STATIC_DIR, DOCS_STATIC_DIR)
    print(f'[build_static] 정적 자산(css/js) → {DOCS_STATIC_DIR}')


def main():
    os.makedirs(DOCS_DATA_DIR, exist_ok=True)

    build_youtube_data()
    build_book_data()
    sync_static_assets()

    # GitHub Pages가 Jekyll로 처리하지 않도록 표시
    nojekyll_path = os.path.join(DOCS_DIR, '.nojekyll')
    if not os.path.exists(nojekyll_path):
        open(nojekyll_path, 'w').close()

    print('[build_static] 완료')


if __name__ == '__main__':
    main()
