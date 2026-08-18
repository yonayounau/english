# ============================================================
# app.py - Flask 애플리케이션 진입점
# 빨모쌤과 함께하는 영어공부 웹앱
# ============================================================

import os
import re
import json
from flask import Flask, render_template, jsonify, request, abort
from dotenv import load_dotenv

from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# .env 파일에서 환경변수 로드
load_dotenv()

# Flask 앱 초기화
app = Flask(__name__)



# ============================================================
# 데이터 로드 헬퍼 함수
# ============================================================

def load_json(filepath):
    """
    JSON 파일을 읽어 Python dict로 반환한다.
    파일이 없거나 파싱 실패 시 빈 dict를 반환한다.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[경고] JSON 파일 로드 실패: {filepath} - {e}")
        return {}


# 데이터 파일 경로 설정 (앱 루트 기준)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
YOUTUBE_JSON = os.path.join(BASE_DIR, 'data', 'youtube_lessons.json')
BOOK_JSON    = os.path.join(BASE_DIR, 'data', 'book_units.json')


def strip_html(text):
    """HTML 태그를 제거하고 순수 텍스트만 반환한다 (검색용)."""
    return re.sub(r'<[^>]+>', '', text or '')


# ============================================================
# 라우트 정의
# ============================================================

# ── 홈 / 날짜 선택 화면 ──────────────────────────────────────
@app.route('/')
def index():
    """
    홈 화면: 학습한 날짜 목록을 캘린더/리스트로 표시
    youtube_lessons.json의 날짜 키를 정렬해서 전달

    검색 기능: 제목(이름)이 최우선 검색 대상이고, 키워드에 들어간
    영어 표현도 검색 대상에 포함한다. 실제 필터링/정렬은 클라이언트
    JS(index.html)에서 하므로, 여기서는 날짜별 키워드 영어 텍스트를
    HTML 태그 없이 미리 합쳐서 넘겨준다.
    """
    data = load_json(YOUTUBE_JSON)
    # 날짜를 내림차순(최신순)으로 정렬
    dates = sorted(data.keys(), reverse=True)

    search_keywords = {
        date: ' '.join(strip_html(s.get('en', '')) for s in data[date].get('keywords', []))
        for date in dates
    }

    return render_template('index.html', dates=dates, lessons=data, search_keywords=search_keywords)


# ── 학습 키워드 화면 ─────────────────────────────────────────
@app.route('/keywords/<date>')
def keywords(date):
    """
    선택한 날짜의 학습 키워드 문장 순차 학습 화면
    :param date: YYYY-MM-DD 형식의 날짜 문자열
    """
    data = load_json(YOUTUBE_JSON)
    lesson = data.get(date)
    if not lesson:
        abort(404)
    return render_template('keywords.html',
                           date=date,
                           lesson=lesson,
                           sentences=lesson.get('keywords', []))


# ── 연습하기 화면 ─────────────────────────────────────────────
@app.route('/practice/<date>')
def practice(date):
    """
    선택한 날짜의 모든 문장을 스크롤 목록으로 표시
    탭하면 해당 문장을 TTS로 재생
    """
    data = load_json(YOUTUBE_JSON)
    lesson = data.get(date)
    if not lesson:
        abort(404)
    return render_template('practice.html',
                           date=date,
                           lesson=lesson)


# ── 나만의 문장 화면 ─────────────────────────────────────────
@app.route('/my-sentences/<date>')
def my_sentences(date):
    """
    선택한 날짜의 '나만의 문장' 순차 학습 화면
    키워드 화면과 동일한 UI 구조, 데이터만 다름
    """
    data = load_json(YOUTUBE_JSON)
    lesson = data.get(date)
    if not lesson:
        abort(404)
    return render_template('my_sentences.html',
                           date=date,
                           lesson=lesson,
                           sentences=lesson.get('my_sentences', []))


# ── 책공부 UNIT 목차 화면 ────────────────────────────────────
@app.route('/book')
def book_units():
    """
    책공부(빨모쌤의 라이브 영어회화) UNIT 목차 리스트 화면
    """
    data = load_json(BOOK_JSON)
    # UNIT 키를 번호 순서로 정렬 (UNIT1, UNIT2, ... 형식)
    def unit_sort_key(item):
        key = item[0]
        m = re.search(r'(\d+)', key)
        return int(m.group(1)) if m else 9999
    units = sorted(data.items(), key=unit_sort_key)
    return render_template('book_units.html', units=units)


# ── 책공부 UNIT 상세 화면 ────────────────────────────────────
@app.route('/book/<unit_id>')
def book_unit_detail(unit_id):
    """
    선택한 UNIT의 문장 순차 학습 화면
    :param unit_id: 'UNIT16', 'UNIT17' 등의 UNIT 키
    """
    data = load_json(BOOK_JSON)
    unit = data.get(unit_id.upper())
    if not unit:
        abort(404)

    # 이전/다음 UNIT 계산 (네비게이션용)
    def unit_num(key):
        m = re.search(r'(\d+)', key)
        return int(m.group(1)) if m else 9999
    all_keys = sorted(data.keys(), key=unit_num)
    cur_idx  = all_keys.index(unit_id.upper()) if unit_id.upper() in all_keys else -1
    prev_unit = all_keys[cur_idx - 1] if cur_idx > 0 else None
    next_unit = all_keys[cur_idx + 1] if cur_idx < len(all_keys) - 1 else None

    return render_template('book_unit_detail.html',
                           unit_id=unit_id.upper(),
                           unit=unit,
                           prev_unit=prev_unit,
                           next_unit=next_unit)


# ── Notion 동기화 API (POST /api/sync) ─────────────────────
@app.route('/api/sync', methods=['POST'])
def sync_notion():
    """
    Notion DB → 로컬 JSON 동기화를 수동으로 트리거하는 API
    sync_notion.py의 함수를 호출하고 결과를 JSON으로 반환
    """
    try:
        # sync_notion 모듈 임포트 후 동기화 실행
        import sync_notion
        result = sync_notion.run_sync()
        return jsonify({'success': True, 'message': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ── API: JSON 데이터 직접 조회 (디버깅용) ───────────────────
@app.route('/api/lessons')
def api_lessons():
    """유튜브 학습 JSON 전체를 반환 (개발/디버깅용)"""
    return jsonify(load_json(YOUTUBE_JSON))


@app.route('/api/books')
def api_books():
    """책 학습 JSON 전체를 반환 (개발/디버깅용)"""
    return jsonify(load_json(BOOK_JSON))


# ── 404 에러 핸들러 ─────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    """404 에러 발생 시 친절한 안내 페이지 렌더링"""
    return render_template('404.html'), 404


# ============================================================
# 자동 동기화 스케줄러
# ============================================================

def scheduled_sync():
    """매일 자동 동기화 실행"""
    print("[스케줄러] Notion 자동 동기화 시작...")
    try:
        import sync_notion
        result = sync_notion.run_sync()
        print(f"[스케줄러] 동기화 완료: {result}")
    except Exception as e:
        print(f"[스케줄러] 동기화 실패: {e}")

# 스케줄러 설정 (앱 실행 시 자동 시작)
scheduler = BackgroundScheduler(timezone="Asia/Seoul")
scheduler.add_job(
    func=scheduled_sync,
    trigger="cron",
    hour=6,          # 매일 오전 6시
    minute=0
)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())  # 앱 종료 시 스케줄러도 정리


# ============================================================
# 앱 실행 (직접 실행 시)
# ============================================================
if __name__ == '__main__':
    # 포트 5000으로 실행, 충돌 시 5001로 변경
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)

