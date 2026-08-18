# ============================================================
# sync_notion.py - Notion API → 로컬 JSON 동기화 스크립트
# 빨모쌤과 함께하는 영어공부 웹앱
#
# 사용법:
#   python sync_notion.py          # 유튜브 + 책 DB 모두 동기화
#   python sync_notion.py youtube  # 유튜브 DB만 동기화
#   python sync_notion.py book     # 책 DB만 동기화
# ============================================================

import os
import json
import re
import sys
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()

# ============================================================
# 설정값
# ============================================================
NOTION_API_KEY       = os.getenv('NOTION_API_KEY')
NOTION_DB_ID_YOUTUBE = os.getenv('NOTION_DB_ID_YOUTUBE')
NOTION_DB_ID_BOOK    = os.getenv('NOTION_DB_ID_BOOK')

# Notion API 기본 URL과 버전
NOTION_BASE_URL = 'https://api.notion.com/v1'
NOTION_VERSION  = '2022-06-28'

# 로컬 저장 경로
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
YOUTUBE_JSON  = os.path.join(BASE_DIR, 'data', 'youtube_lessons.json')
BOOK_JSON     = os.path.join(BASE_DIR, 'data', 'book_units.json')


# ============================================================
# Notion API 공통 헬퍼 함수
# ============================================================

def get_headers():
    """
    Notion API 요청에 필요한 인증 헤더를 반환한다.
    """
    return {
        'Authorization': f'Bearer {NOTION_API_KEY}',
        'Notion-Version': NOTION_VERSION,
        'Content-Type': 'application/json'
    }


def _request_with_retry(method, url, max_retries=5, **kwargs):
    """
    429 Too Many Requests 발생 시 자동으로 대기 후 재시도한다.

    :param method: 'get' 또는 'post'
    :param url: 요청 URL
    :param max_retries: 최대 재시도 횟수
    :return: requests.Response 객체
    """
    for attempt in range(max_retries):
        if method == 'get':
            response = requests.get(url, **kwargs)
        else:
            response = requests.post(url, **kwargs)

        if response.status_code == 429:
            # Retry-After 헤더가 있으면 그 시간만큼, 없으면 지수 백오프
            retry_after = int(response.headers.get('Retry-After', 2 ** attempt))
            wait = max(retry_after, 1)
            print(f'    [429] 요청 한도 초과. {wait}초 후 재시도... (시도 {attempt + 1}/{max_retries})')
            time.sleep(wait)
            continue

        return response

    # 최대 재시도 후에도 실패하면 마지막 응답 반환 (raise_for_status로 처리)
    return response


def query_database(db_id, filter_body=None, sorts=None):
    """
    Notion DB를 쿼리하여 전체 페이지 목록을 반환한다.
    페이지네이션(cursor)을 지원하여 100개 이상도 모두 가져온다.

    :param db_id: Notion 데이터베이스 ID
    :param filter_body: Notion 필터 조건 (dict, 선택적)
    :param sorts: 정렬 조건 (list, 선택적)
    :return: 페이지 객체 목록 (list)
    """
    url = f'{NOTION_BASE_URL}/databases/{db_id}/query'
    results = []
    next_cursor = None

    while True:
        body = {}
        if filter_body:
            body['filter'] = filter_body
        if sorts:
            body['sorts'] = sorts
        if next_cursor:
            body['start_cursor'] = next_cursor

        response = _request_with_retry('post', url, headers=get_headers(), json=body)
        response.raise_for_status()
        data = response.json()

        results.extend(data.get('results', []))

        # 요청 간 딜레이 (Notion API: 초당 3회 제한)
        time.sleep(0.35)

        if data.get('has_more'):
            next_cursor = data.get('next_cursor')
        else:
            break

    return results


def get_block_children(block_id):
    """
    Notion 블록의 자식 블록 목록을 반환한다. (페이지네이션 지원)

    :param block_id: 블록(또는 페이지) ID
    :return: 블록 객체 목록 (list)
    """
    url = f'{NOTION_BASE_URL}/blocks/{block_id}/children'
    results = []
    next_cursor = None

    while True:
        params = {}
        if next_cursor:
            params['start_cursor'] = next_cursor

        response = _request_with_retry('get', url, headers=get_headers(), params=params)
        response.raise_for_status()
        data = response.json()

        results.extend(data.get('results', []))

        # 요청 간 딜레이 (Notion API: 초당 3회 제한)
        time.sleep(0.35)

        if data.get('has_more'):
            next_cursor = data.get('next_cursor')
        else:
            break

    return results


# 하위 호환성을 위한 별칭
def get_page_blocks(page_id):
    return get_block_children(page_id)


# ============================================================
# 텍스트 파싱 헬퍼
# ============================================================

# Notion 텍스트 색상 → CSS 색상 매핑 (업데이트 v2: 색깔 서식 보존)
_NOTION_TEXT_COLORS = {
    'gray': '#787774', 'brown': '#976D57', 'orange': '#CC782F',
    'yellow': '#C29343', 'green': '#548164', 'blue': '#487CA5',
    'purple': '#8A67AB', 'pink': '#B84C75', 'red': '#D44C47',
}
_NOTION_BG_COLORS = {
    'gray_background': '#F1F1EF', 'brown_background': '#F3EEEE',
    'orange_background': '#F8ECDF', 'yellow_background': '#FBF3DB',
    'green_background': '#EDF3EC', 'blue_background': '#E7F3F8',
    'purple_background': '#F6F3F9', 'pink_background': '#F9F2F5',
    'red_background': '#FDEBEC',
}


def notion_color_style(color):
    """Notion 색상 어노테이션을 인라인 CSS 스타일 문자열로 변환한다 ('' = 기본색)."""
    if color in _NOTION_TEXT_COLORS:
        return f'color:{_NOTION_TEXT_COLORS[color]}'
    if color in _NOTION_BG_COLORS:
        return f'background-color:{_NOTION_BG_COLORS[color]}'
    return ''


def rich_text_to_lines(rich_text_list):
    """
    Notion rich_text 배열을 줄바꿈('\\n', shift+enter) 기준으로 여러 줄로 나눈다.
    각 줄은 run 목록 [{'text','bold','color'}, ...] 형태로, bold/색깔 서식을
    글자 단위로 유지한다 (한 블록 안에서 줄마다 서식이 달라도 보존됨).

    :param rich_text_list: Notion API의 rich_text 배열
    :return: [[run, ...], [run, ...], ...] (줄 목록)
    """
    lines = [[]]
    for rt in rich_text_list:
        text  = rt.get('plain_text', '')
        ann   = rt.get('annotations', {})
        bold  = ann.get('bold', False)
        color = ann.get('color', 'default')

        segments = text.split('\n')
        for i, seg in enumerate(segments):
            if seg:
                lines[-1].append({'text': seg, 'bold': bold, 'color': color})
            if i < len(segments) - 1:
                lines.append([])

    return lines


def runs_to_plain(runs):
    """run 목록을 순수 텍스트로 합친다."""
    return ''.join(r['text'] for r in runs)


def runs_bold_words(runs):
    """run 목록에서 bold로 표시된 단어들을 추출한다."""
    return [r['text'].strip() for r in runs if r.get('bold') and r['text'].strip()]


def render_runs(runs):
    """
    run 목록을 HTML 문자열로 렌더링한다.
    bold는 <strong>, 색깔은 <span style="..."> 로 감싸 서식을 보존한다.
    """
    parts = []
    for r in runs:
        text = r['text']
        if not text:
            continue
        piece = text
        if r.get('bold'):
            piece = f'<strong>{piece}</strong>'
        style = notion_color_style(r.get('color', 'default'))
        if style:
            piece = f'<span style="{style}">{piece}</span>'
        parts.append(piece)
    return ''.join(parts)


def slice_runs(runs, start, end):
    """run 목록에서 순수 텍스트 기준 [start, end) 구간에 해당하는 부분만 잘라 반환한다."""
    result = []
    pos = 0
    for r in runs:
        text = r['text']
        r_start, r_end = pos, pos + len(text)
        pos = r_end
        if r_end <= start or r_start >= end:
            continue
        s = max(start, r_start) - r_start
        e = min(end, r_end) - r_start
        piece = text[s:e]
        if piece:
            result.append({'text': piece, 'bold': r.get('bold', False), 'color': r.get('color', 'default')})
    return result


def trim_runs(runs):
    """run 목록 앞뒤의 공백을 제거한다 (문자열의 strip()과 동일한 효과)."""
    plain = runs_to_plain(runs)
    start = len(plain) - len(plain.lstrip())
    end   = start + len(plain.strip())
    if start == 0 and end == len(plain):
        return runs
    return slice_runs(runs, start, end)


def get_property_text(page, prop_name):
    """
    Notion 페이지의 특정 속성(property)에서 텍스트를 추출한다.

    :param page: Notion 페이지 객체
    :param prop_name: 속성 이름 문자열
    :return: 텍스트 문자열 (없으면 빈 문자열)
    """
    props = page.get('properties', {})
    prop  = props.get(prop_name, {})
    ptype = prop.get('type', '')

    if ptype == 'title':
        items = prop.get('title', [])
    elif ptype == 'rich_text':
        items = prop.get('rich_text', [])
    elif ptype == 'url':
        return prop.get('url', '') or ''
    elif ptype == 'date':
        date_obj = prop.get('date') or {}
        return date_obj.get('start', '') or ''
    else:
        return ''

    return ''.join(rt.get('plain_text', '') for rt in items)


# ============================================================
# 언어 감지 헬퍼
# ============================================================

def is_korean(text):
    """한글 유니코드 포함 여부로 한국어 판별"""
    return bool(re.search(r'[가-힣ㄱ-ㅎㅏ-ㅣ]', text))


def is_english_dominant(text):
    """영어 알파벳이 있고 한글이 없으면 영어로 판별"""
    return bool(re.search(r'[a-zA-Z]', text)) and not is_korean(text)


def find_en_ko_spans(text):
    """
    텍스트에서 영어/한국어 구간을 판별한다.
    규칙 (우선순위 순):
    1. '|' 구분자가 있으면 좌=영어, 우=한국어
    2. ' : ' (공백포함 콜론) 구분자 → 좌가 영어 우세이면 영어, 아니면 한국어 설명
    3. 한글이 없으면 영어 (ko=None)
    4. 영어가 없으면 한국어 (en=None)
    5. 혼재: 전체를 한국어로 처리 (en=None)

    문자열 대신 (start, end) 인덱스 구간을 반환하므로, 이를 이용해
    rich text 서식(bold/색깔)이 살아있는 상태로 잘라낼 수 있다.

    :param text: 검사할 순수 텍스트 (앞뒤 공백 없는 상태여야 함)
    :return: (en_span, ko_span) - 각각 (start, end) 튜플 또는 None
    """
    n = len(text)

    # 1. '|' 구분자
    idx = text.find(' | ')
    if idx != -1:
        return (0, idx), (idx + 3, n)
    idx = text.find('|')
    if idx != -1 and not text.startswith('|'):
        left, right = text[:idx].strip(), text[idx + 1:].strip()
        if left and right:
            return (0, idx), (idx + 1, n)

    # 2. ' : ' 구분자 (공백 포함)
    # 패턴: "영어 표현 : 한국어 뜻" 또는 "한국어 : 영어 예문"
    colon_match = re.search(r'\s:\s', text)
    if colon_match:
        left  = text[:colon_match.start()].strip()
        right = text[colon_match.end():].strip()
        if left and right:
            # 왼쪽이 영어 우세이면 영어=left, 한국어=right
            # (대화형 A:/B: 패턴은 아래에서 처리하므로 여기서는 단순 분리)
            if is_english_dominant(left) or not is_korean(left):
                return (0, colon_match.start()), (colon_match.end(), n)
            else:
                # 한국어 : 영어 형태 → 뒤집기
                if is_english_dominant(right) or not is_korean(right):
                    return (colon_match.end(), n), (0, colon_match.start())
                # 둘 다 한국어면 전체 한국어
                return None, (0, n)

    # 3. 한글 없음 → 영어
    if not is_korean(text):
        return (0, n), None

    # 4. 영어 없음 → 한국어
    if not re.search(r'[a-zA-Z]', text):
        return None, (0, n)

    # 5. 혼재 → 한국어
    return None, (0, n)


def split_runs_en_ko(runs):
    """
    한 줄의 run 목록(서식 포함)을 영어/한국어 run 목록으로 분리한다.
    find_en_ko_spans()의 판별 규칙을 그대로 적용하되, 문자열이 아닌 run 단위로
    잘라내므로 분리 후에도 bold/색깔 서식이 그대로 유지된다.

    :param runs: [{'text','bold','color'}, ...]
    :return: (en_runs, ko_runs) 튜플 (각각 run 목록, 없으면 빈 리스트)
    """
    runs = trim_runs(runs)
    plain = runs_to_plain(runs)
    if not plain:
        return [], []

    en_span, ko_span = find_en_ko_spans(plain)
    en_runs = trim_runs(slice_runs(runs, *en_span)) if en_span else []
    ko_runs = trim_runs(slice_runs(runs, *ko_span)) if ko_span else []
    return en_runs, ko_runs


# ============================================================
# 책 파싱용 헬퍼 - 블록에서 문장 쌍 추출
# ============================================================

def get_block_rich_text(block):
    """
    블록 타입에 따라 rich_text 배열을 반환한다.
    지원: bulleted_list_item, numbered_list_item, paragraph,
          quote, callout, to_do, toggle
    """
    btype = block.get('type', '')
    block_data = block.get(btype, {})
    return block_data.get('rich_text', [])


def split_consecutive_pairs(items):
    """
    연속된 영어 단독 항목 / 한국어 단독 항목을 하나의 문장 쌍으로 합친다.
    업데이트 v2: 아래 두 가지 순서를 모두 처리한다.
    - [영어] 다음에 [한국어]가 오는 경우 (일반적인 순서)
    - [한국어] 다음에 [영어]가 오는 경우 (뒤바뀐 순서)
    두 경우 모두 최종 결과는 en이 먼저, ko가 나중인 항목으로 합쳐진다.
    """
    if not items:
        return []

    paired = []
    i = 0
    while i < len(items):
        item = items[i]
        en, ko = item.get('en', ''), item.get('ko', '')

        if i + 1 < len(items):
            nxt = items[i + 1]
            n_en, n_ko = nxt.get('en', ''), nxt.get('ko', '')

            # 영어 단독 → 한국어 단독
            if en and not ko and n_ko and not n_en:
                paired.append({
                    'en': en,
                    'ko': n_ko,
                    'bold_words': item.get('bold_words', []) + nxt.get('bold_words', [])
                })
                i += 2
                continue

            # 한국어 단독 → 영어 단독 (순서가 뒤바뀐 경우)
            if ko and not en and n_en and not n_ko:
                paired.append({
                    'en': n_en,
                    'ko': ko,
                    'bold_words': item.get('bold_words', []) + nxt.get('bold_words', [])
                })
                i += 2
                continue

        paired.append(item)
        i += 1

    return paired


def collect_toggle_text_lines(blocks, depth=0, max_depth=5):
    """
    toggle 블록과 그 자식 블록들의 텍스트를 전부 한국어 설명으로 간주하여
    영어/한국어 분리 없이 원문 그대로 한 줄씩 수집한다. (업데이트 v3)

    :param blocks: toggle 블록(들)의 자식 블록 목록
    :param depth: 현재 재귀 깊이
    :param max_depth: 최대 재귀 깊이
    :return: 텍스트 줄 목록 (list[str])
    """
    if depth > max_depth:
        return []

    lines = []
    supported = (
        'bulleted_list_item', 'numbered_list_item',
        'paragraph', 'quote', 'callout', 'to_do', 'toggle'
    )

    for block in blocks:
        btype = block.get('type', '')
        if btype not in supported:
            continue

        rich_texts = get_block_rich_text(block)
        text = ''.join(rt.get('plain_text', '') for rt in rich_texts).strip()
        if text:
            lines.extend(line for line in (s.strip() for s in text.split('\n')) if line)

        if block.get('has_children'):
            child_blocks = get_block_children(block['id'])
            lines.extend(collect_toggle_text_lines(child_blocks, depth + 1, max_depth))

    return lines


# "cf." (대소문자 무관)로 시작하는 줄은 독립 연습 문장이 아니라 참고 메모로
# 취급해 바로 위 문장의 'ko'에 이어붙인다 (업데이트 v3)
CF_NOTE_PATTERN = re.compile(r'^cf\.?(\s+|$)', re.IGNORECASE)


def collect_sentences_from_blocks(blocks, depth=0, max_depth=5):
    """
    블록 목록에서 영어/한국어 문장 쌍을 재귀적으로 수집한다.

    기획서의 파싱 규칙:
    - bulleted/numbered/paragraph 모두 처리
    - Bulleted list item 아래의 자식 텍스트는 '한 세트' (부모와 같은 섹션)
    - 대화형 (A:/B: 패턴)도 각각 분리해서 수집
    - 영어/한국어가 한 블록에 함께 있으면 자동 분리
    - ':' 구분자, '|' 구분자, 연속 영어-한국어 쌍 처리
    - toggle 블록은 헤더 줄은 건너뛰고 자식 내용만 영어/한국어 분리 없이
      통째로 한국어로 간주해 바로 위 문장 항목의 'ko'에 이어붙인다 (업데이트 v3)
    - "cf."로 시작하는 줄은 독립 카드로 만들지 않고 바로 위 문장의 'ko'에
      참고 메모로 이어붙인다 (업데이트 v3)
    - 빈 블록, 구분선(divider) 등은 건너뜀

    :param blocks: Notion 블록 목록
    :param depth: 현재 재귀 깊이
    :param max_depth: 최대 재귀 깊이
    :return: [{'en': str, 'ko': str, 'bold_words': list}, ...]
    """
    if depth > max_depth:
        return []

    raw_items = []   # 아직 쌍으로 합치기 전 항목들
    # 대화형(A:/B:) 패턴
    dialog_pattern = re.compile(r'^([A-Za-z])\s*:\s*(.+)$', re.DOTALL)

    supported = (
        'bulleted_list_item', 'numbered_list_item',
        'paragraph', 'quote', 'callout', 'to_do', 'toggle'
    )

    def build_item(line_runs):
        """
        한 줄(run 목록)에서 문장 항목({'en','ko','bold_words'})을 만든다.
        대화형(A:/B:) 라인은 화자 표시를 유지한 채 영/한을 분리하고,
        일반 라인은 find_en_ko_spans 규칙에 따라 분리한다.
        en 필드는 bold/색깔 서식이 살아있는 HTML, ko 필드는 항상 순수 텍스트다.
        """
        plain = runs_to_plain(line_runs)
        dialog_match = dialog_pattern.match(plain)

        if dialog_match:
            speaker = dialog_match.group(1).upper()
            content_runs = trim_runs(slice_runs(line_runs, dialog_match.start(2), len(plain)))
            en_runs, ko_runs = split_runs_en_ko(content_runs)
            en_html  = render_runs(en_runs)
            ko_plain = runs_to_plain(ko_runs)
            return {
                'en': f'{speaker}: {en_html}' if en_html else '',
                'ko': f'{speaker}: {ko_plain}' if ko_plain else '',
                'bold_words': runs_bold_words(en_runs)
            }

        en_runs, ko_runs = split_runs_en_ko(line_runs)
        # en으로 분류된 내용이 실제로는 한글인 경우 보정
        if en_runs and is_korean(runs_to_plain(en_runs)):
            en_runs, ko_runs = [], en_runs
        return {
            'en': render_runs(en_runs),
            'ko': runs_to_plain(ko_runs),
            'bold_words': runs_bold_words(en_runs)
        }

    def merge_note_into(target_items, note_text, bold_words=None):
        """
        note_text를 target_items의 마지막 항목 'ko'에 이어붙인다.
        target_items가 비어 있으면 아무것도 하지 않고 False를 반환한다.
        """
        if not target_items:
            return False
        prev = target_items[-1]
        prev['ko'] = f"{prev['ko']}\n\n{note_text}" if prev.get('ko') else note_text
        if bold_words:
            prev['bold_words'] = prev.get('bold_words', []) + bold_words
        return True

    def merge_note(note_text, bold_words=None):
        """
        note_text를 별도 카드로 만들지 않고 바로 위 문장 항목의 'ko'에 이어붙인다.
        붙일 앞 항목이 없으면(맨 처음 등장) 단독 한국어 항목으로 남긴다.
        """
        if not merge_note_into(raw_items, note_text, bold_words):
            raw_items.append({'en': '', 'ko': note_text, 'bold_words': bold_words or []})

    for block in blocks:
        btype = block.get('type', '')

        # ── toggle 블록: 자기 자신(헤더 줄)은 건너뛰고, 접힌 자식 내용만
        #    영어/한국어 분리 없이 통째로 한국어로 취급해 바로 위 문장 항목의
        #    'ko'에 이어붙인다 (업데이트 v3) ──────────────────────────────
        if btype == 'toggle':
            if block.get('has_children'):
                child_blocks = get_block_children(block['id'])
                toggle_lines = collect_toggle_text_lines(child_blocks)
                if toggle_lines:
                    merge_note('\n'.join(toggle_lines))
            continue

        if btype not in supported:
            # heading 내부의 자식 블록은 별도 처리하지 않음
            continue

        rich_texts = get_block_rich_text(block)

        # 줄바꿈(shift+enter, rule 1/2) 기준으로 나누고 빈 줄은 제거
        lines = [trim_runs(line) for line in rich_text_to_lines(rich_texts)]
        lines = [line for line in lines if runs_to_plain(line)]

        # ── 빈 블록: 자식 블록만 처리 ────────────────────────
        if not lines:
            if block.get('has_children'):
                child_blocks = get_block_children(block['id'])
                child_items = collect_sentences_from_blocks(child_blocks, depth + 1, max_depth)
                raw_items.extend(child_items)
            continue

        # "cf." (대소문자 무관)로 시작하는 줄은 독립 카드가 아니라 바로 위 문장의
        # 'ko'에 이어붙이는 참고 메모로 취급한다 (업데이트 v3).
        # 같은 블록 안에서 앞서 처리된 줄이 있으면 그쪽에 먼저 붙이고(줄 순서를
        # 지켜야 하므로 line_items가 아직 raw_items로 옮겨지기 전임), 이 줄이
        # 블록의 첫 줄이면 이전 블록에서 만들어진 raw_items의 마지막 항목에 붙인다.
        line_items = []
        for line in lines:
            plain = runs_to_plain(line)
            if CF_NOTE_PATTERN.match(plain):
                if not merge_note_into(line_items, plain):
                    merge_note(plain)
                continue
            line_items.append(build_item(line))

        if len(line_items) >= 2:
            # 여러 줄: 각 줄을 개별 처리 후 연속 쌍 합치기 (rule 1/2)
            raw_items.extend(split_consecutive_pairs(line_items))
        elif len(line_items) == 1:
            item = line_items[0]
            if item['en'] or item['ko']:
                raw_items.append(item)

        # ── 자식 블록 재귀 처리 ──────────────────────────────────
        if block.get('has_children'):
            child_blocks = get_block_children(block['id'])
            child_items = collect_sentences_from_blocks(child_blocks, depth + 1, max_depth)
            raw_items.extend(child_items)

    # 블록 간 연속 쌍(rule 3, enter로 나뉜 블록)은 전체 문서 순서가 다 모인
    # 최상위 레벨에서 한 번만 합친다 (중간 depth에서 미리 합치면 재귀 경계에서
    # 유효한 쌍이 잘못 갈릴 수 있음).
    if depth == 0:
        return split_consecutive_pairs(raw_items)
    return raw_items


# ============================================================
# 유튜브 학습 DB 동기화
# ============================================================

def sync_youtube_db(force=False):
    """
    Notion 유튜브 학습 DB를 동기화하여 data/youtube_lessons.json 저장.

    증분 동기화: 기존 JSON에 이미 있는 날짜는 API 요청 없이 건너뛴다.
    force=True 이면 전체 재동기화한다.

    Notion DB 구조 가정:
      - 날짜(Date) 속성: '날짜' 또는 'Date'
      - 유튜브 URL 속성: 'URL' 또는 'YouTube'
      - 이름 속성: '이름' 또는 'Name' 또는 title 타입
    """
    print('[동기화] 유튜브 학습 DB 동기화 시작...')

    # ── 기존 JSON 로드 (증분 동기화용) ──────────────────────────
    existing = {}
    if not force and os.path.exists(YOUTUBE_JSON):
        try:
            with open(YOUTUBE_JSON, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            print(f'    기존 데이터 {len(existing)}개 날짜 로드됨 (새 항목만 동기화)')
        except Exception:
            existing = {}
    # ─────────────────────────────────────────────────────────────

    pages = query_database(
        NOTION_DB_ID_YOUTUBE,
        sorts=[{'property': '날짜', 'direction': 'descending'}]
    )

    print(f'    Notion에서 {len(pages)}개 페이지 목록 수신')

    # 기존 데이터를 result의 베이스로 사용
    result = dict(existing)
    new_count = 0
    skip_count = 0

    for i, page in enumerate(pages, 1):
        # 날짜 추출 (YYYY-MM-DD 형식)
        date_str = get_property_text(page, '날짜') or get_property_text(page, 'Date')
        if not date_str:
            continue

        date_key = date_str[:10]

        # ── 증분 동기화: 이미 있는 날짜는 건너뜀 ────────────────
        if date_key in existing:
            skip_count += 1
            continue
        # ─────────────────────────────────────────────────────────

        print(f'    [{i}/{len(pages)}] {date_key} 처리 중...')

        # 유튜브 URL 추출
        youtube_url = (
            get_property_text(page, 'URL') or
            get_property_text(page, 'YouTube URL') or
            get_property_text(page, 'YouTube') or
            ''
        )

        # 페이지 이름(title) 추출
        page_name = ''
        for prop_name, prop_data in page.get('properties', {}).items():
            if prop_data.get('type') == 'title':
                title_items = prop_data.get('title', [])
                page_name = ''.join(rt.get('plain_text', '') for rt in title_items).strip()
                break
        if not page_name:
            page_name = (
                get_property_text(page, '이름') or
                get_property_text(page, 'Name') or
                ''
            )

        # 페이지 블록에서 키워드·나만의 문장 파싱
        blocks = get_block_children(page['id'])

        keyword_blocks     = []
        my_sentence_blocks = []
        current_section    = 'keywords'

        for block in blocks:
            btype = block.get('type', '')

            if btype in ('heading_1', 'heading_2', 'heading_3'):
                heading_text = ''.join(
                    rt.get('plain_text', '')
                    for rt in block[btype].get('rich_text', [])
                ).strip().lower()
                if '나만의' in heading_text or 'my sentence' in heading_text:
                    current_section = 'my_sentences'
                elif '한글' in heading_text:
                    # 업데이트: '✔️ 한글' 섹션은 키워드 학습에서 제외한다
                    current_section = 'skip'
                else:
                    # '✔️학습 키워드', '✔️ 영문' 등은 모두 키워드 섹션으로 취급
                    current_section = 'keywords'
                continue

            if current_section == 'keywords':
                keyword_blocks.append(block)
            elif current_section == 'my_sentences':
                my_sentence_blocks.append(block)
            # current_section == 'skip'인 경우 아무 목록에도 담지 않음

        keywords     = collect_sentences_from_blocks(keyword_blocks)
        my_sentences = collect_sentences_from_blocks(my_sentence_blocks)

        for idx, s in enumerate(keywords):
            s['id'] = idx + 1
        for idx, s in enumerate(my_sentences):
            s['id'] = idx + 1

        result[date_key] = {
            'name':        page_name,
            'youtube_url': youtube_url,
            'keywords':    keywords,
            'my_sentences': my_sentences
        }
        new_count += 1

        # 10개마다 중간 저장 (중간에 중단돼도 데이터 보존)
        if new_count % 10 == 0:
            with open(YOUTUBE_JSON, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f'    중간 저장 완료 ({new_count}개 신규)')

    # 최종 JSON 저장
    os.makedirs(os.path.dirname(YOUTUBE_JSON), exist_ok=True)
    with open(YOUTUBE_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'[동기화 완료] 총 {len(result)}개 (신규 {new_count}개, 건너뜀 {skip_count}개) → {YOUTUBE_JSON}')
    return f'유튜브 학습 데이터 {len(result)}개 저장 완료 (신규 {new_count}개)'



# ============================================================
# 책 학습 DB 동기화 (업데이트 v1 - 전면 개선)
# ============================================================

def sync_book_db():
    """
    Notion 책 학습 페이지 블록을 파싱하여 data/book_units.json 저장.

    [업데이트 v1 변경사항]
    - NOTION_DB_ID_BOOK 값은 실제로는 DB ID가 아니라 Notion 페이지 ID
    - 해당 페이지의 모든 블록을 직접 가져와 heading_3 기준으로 UNIT 분류
    - bulleted_list_item, numbered_list_item, paragraph 등 다양한 블록 타입 파싱
    - 들여쓰기된 자식 블록 재귀 처리
    - 영어/한국어 자동 감지 및 분리
    """
    print('[동기화] 책 학습 페이지 블록 동기화 시작...')
    print(f'         PAGE ID: {NOTION_DB_ID_BOOK}')

    # 페이지 최상위 블록 전체 가져오기
    top_blocks = get_block_children(NOTION_DB_ID_BOOK)
    print(f'         최상위 블록 수: {len(top_blocks)}')

    result      = {}
    total_units = 0

    # ── heading_3 기준으로 UNIT 분류 ──────────────────────────────
    current_unit_key    = None
    current_unit_title  = None
    current_unit_blocks = []  # 현재 UNIT에 속하는 블록들

    def flush_unit():
        """현재 수집된 UNIT 블록을 파싱하여 result에 저장"""
        nonlocal current_unit_key, current_unit_title, current_unit_blocks, total_units
        if not current_unit_key or not current_unit_blocks:
            return

        sentences = collect_sentences_from_blocks(current_unit_blocks)

        # ID 부여
        for idx, s in enumerate(sentences):
            s['id'] = idx + 1

        if sentences:  # 문장이 있는 UNIT만 저장
            # 중복 키 방지
            save_key = current_unit_key
            suffix   = 2
            while save_key in result:
                save_key = f'{current_unit_key}_{suffix}'
                suffix  += 1

            result[save_key] = {
                'title':     current_unit_title,
                'sentences': sentences
            }
            total_units += 1
            print(f'    → {save_key}: {current_unit_title} ({len(sentences)}문장)')

    for block in top_blocks:
        btype = block.get('type', '')

        if btype == 'heading_3':
            # 이전 UNIT 저장
            flush_unit()

            # 새 UNIT 시작
            heading_rich = block['heading_3'].get('rich_text', [])
            heading_text = ''.join(
                rt.get('plain_text', '') for rt in heading_rich
            ).strip()

            # UNIT 키 생성 (예: "UNIT 1. 표현이름" → "UNIT1")
            unit_key = _make_unit_key(heading_text)
            if not unit_key:
                # UNIT 번호 없는 heading_3 → 텍스트 앞 30자로 키 생성
                safe_key = re.sub(r'[^\w가-힣]', '_', heading_text)[:30].strip('_')
                unit_key = safe_key if safe_key else f'UNIT_{total_units + 1}'

            current_unit_key    = unit_key
            current_unit_title  = heading_text
            current_unit_blocks = []

        elif btype in ('heading_1', 'heading_2'):
            # heading_1/2는 대단원 구분 역할 → 현재 UNIT 저장 후 초기화
            flush_unit()
            current_unit_key    = None
            current_unit_title  = None
            current_unit_blocks = []

        else:
            # 현재 UNIT에 블록 추가 (UNIT 범위 밖이면 무시)
            if current_unit_key is not None:
                current_unit_blocks.append(block)

    # 마지막 UNIT 저장
    flush_unit()

    # JSON 파일로 저장
    os.makedirs(os.path.dirname(BOOK_JSON), exist_ok=True)
    with open(BOOK_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f'[동기화 완료] 책 학습 데이터 {total_units}개 UNIT 저장됨 → {BOOK_JSON}')
    return f'책 학습 데이터 {total_units}개 UNIT 저장 완료'



def _make_unit_key(text):
    """
    텍스트에서 UNIT 키를 생성한다.
    예: "UNIT 1. 어쩌고" → "UNIT1"
        "1단원"           → "UNIT1"
        "UNIT16"          → "UNIT16"
        "16"              → "UNIT16"

    :param text: heading 텍스트
    :return: 'UNIT숫자' 형식 문자열, 숫자가 없으면 빈 문자열
    """
    # UNIT 숫자 패턴 우선 추출
    match = re.search(r'(?:UNIT|unit|Unit|단원|chapter|ch)[\s\._-]*(\d+)', text, re.IGNORECASE)
    if match:
        return f'UNIT{match.group(1)}'

    # 텍스트 앞에 오는 숫자만 있는 경우
    match = re.match(r'^(\d+)[\.\s]', text)
    if match:
        return f'UNIT{match.group(1)}'

    return ''


# ============================================================
# 동기화 실행 함수 (Flask app.py에서 호출)
# ============================================================

def run_sync(target='all', force=False):
    """
    동기화를 실행하고 결과 메시지를 반환한다.

    :param target: 'all' | 'youtube' | 'book'
    :param force: True이면 유튜브 DB의 증분 동기화(기존 날짜 건너뛰기)를 무시하고
                  모든 날짜를 다시 파싱한다. 파싱 규칙이 바뀐 뒤 기존 데이터를
                  새 규칙으로 갱신할 때 사용한다.
    :return: 결과 메시지 문자열
    """
    messages = []

    if target in ('all', 'youtube'):
        msg = sync_youtube_db(force=force)
        messages.append(msg)

    if target in ('all', 'book'):
        msg = sync_book_db()
        messages.append(msg)

    return ' / '.join(messages)


# ============================================================
# 직접 실행 시 (CLI 사용)
# ============================================================
if __name__ == '__main__':
    # 사용법: python sync_notion.py [all|youtube|book] [--force]
    # --force: 유튜브 DB의 증분 동기화를 끄고 모든 날짜를 다시 파싱
    args   = sys.argv[1:]
    force  = '--force' in args
    args   = [a for a in args if a != '--force']
    target = args[0] if args else 'all'

    if not NOTION_API_KEY:
        print('[오류] NOTION_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.')
        sys.exit(1)

    print(f'[시작] Notion 동기화 대상: {target}' + (' (전체 재동기화)' if force else ''))
    result = run_sync(target, force=force)
    print(f'[완료] {result}')
