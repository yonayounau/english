/* ============================================================
   static-helpers.js - GitHub Pages 정적 사이트 전용 공용 유틸
   (Flask 템플릿은 사용하지 않음, docs/ 정적 페이지에서만 사용)
   ============================================================ */

/**
 * URL 쿼리 파라미터 값을 읽는다.
 * @param {string} name - 파라미터 이름
 * @returns {string|null}
 */
function getQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

/**
 * HTML 속성 값으로 안전하게 넣을 수 있도록 특수문자를 이스케이프한다.
 * (Jinja2의 자동 이스케이프를 클라이언트 쪽에서 대체)
 * @param {string} str
 * @returns {string}
 */
function escapeAttr(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * fetch로 JSON을 가져온다. 실패(404 등)하면 null을 반환한다.
 * @param {string} url
 * @returns {Promise<any|null>}
 */
async function fetchJsonSafe(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.error('[static-helpers] fetch 실패:', url, err);
    return null;
  }
}

/**
 * YYYY-MM-DD → YY/MM/DD 형식으로 변환한다.
 * @param {string} date
 * @returns {string}
 */
function formatDateDisplay(date) {
  const parts = date.split('-');
  return parts[0].slice(2) + '/' + parts[1] + '/' + parts[2];
}
