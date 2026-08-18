/* ============================================================
   ko-en-toggle.js - 한국어 표시 on/off 토글 컴포넌트
   ============================================================ */

/**
 * KoEnToggle 클래스
 * 한국어 문장 표시를 on/off 토글하는 컴포넌트
 * 
 * 사용법:
 *   const toggle = new KoEnToggle('#ko-toggle-btn', '.sentence-ko');
 *   toggle.toggle();           // 수동 토글
 *   toggle.setVisible(false);  // 숨기기
 */
class KoEnToggle {
  /**
   * @param {string} btnSelector   - 토글 버튼 CSS 선택자
   * @param {string} targetSelector - 한국어 텍스트 요소 CSS 선택자
   */
  constructor(btnSelector, targetSelector) {
    this.btn     = document.querySelector(btnSelector);
    this.targets = document.querySelectorAll(targetSelector);
    this.visible = true; // 기본값: 한국어 표시 ON

    if (!this.btn) return; // 버튼이 없으면 초기화 중단

    // 저장된 설정 불러오기 (사용자가 껐던 상태 유지)
    const saved = localStorage.getItem('koVisible');
    if (saved !== null) {
      this.visible = saved === 'true';
    }

    // 초기 상태 적용
    this._applyState();

    // 버튼 클릭 이벤트 등록
    this.btn.addEventListener('click', () => this.toggle());
  }

  /**
   * 현재 상태를 반전시킨다 (ON → OFF, OFF → ON).
   */
  toggle() {
    this.visible = !this.visible;
    this._applyState();

    // 로컬스토리지에 설정 저장 (다음 방문 시 유지)
    localStorage.setItem('koVisible', String(this.visible));
  }

  /**
   * 한국어 표시 여부를 명시적으로 설정한다.
   * @param {boolean} visible - true: 표시, false: 숨김
   */
  setVisible(visible) {
    this.visible = visible;
    this._applyState();
  }

  /**
   * 현재 표시 대상 요소들을 업데이트한다.
   * 화면 전환 시 새 요소에 적용할 때 사용.
   * @param {string} targetSelector - 새 CSS 선택자
   */
  updateTargets(targetSelector) {
    this.targets = document.querySelectorAll(targetSelector);
    this._applyState();
  }

  /**
   * 상태를 DOM에 반영한다.
   * @private
   */
  _applyState() {
    // 모든 한국어 요소에 hidden 클래스 토글
    this.targets.forEach(el => {
      if (this.visible) {
        el.classList.remove('hidden');
      } else {
        el.classList.add('hidden');
      }
    });

    // 버튼 UI 업데이트
    if (this.btn) {
      if (this.visible) {
        this.btn.classList.add('active');
        this.btn.querySelector('.toggle-text').textContent = '한국어 ON';
      } else {
        this.btn.classList.remove('active');
        this.btn.querySelector('.toggle-text').textContent = '한국어 OFF';
      }
    }
  }
}
