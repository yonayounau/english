/* ============================================================
   sentence-player.js - 문장 순차 재생 플레이어 컴포넌트
   
   학습 키워드, 나만의 문장, 책공부 UNIT 상세 화면에서 공용으로 사용.
   문장 표시, 이전/다음 이동, 탭으로 다음 문장, 목차 기능을 제공한다.
   ============================================================ */

/**
 * SentencePlayer 클래스
 * 문장을 순차적으로 재생하고 이동하는 핵심 컴포넌트
 * 
 * 사용법:
 *   const player = new SentencePlayer(sentences, ttsInstance, {
 *     onIndexChange: (idx) => console.log(idx)
 *   });
 */
class SentencePlayer {
  /**
   * @param {Array}      sentences  - 문장 배열 [{id, en, ko, bold_words}, ...]
   * @param {TTSControl} tts        - TTSControl 인스턴스
   * @param {Object}     options    - 옵션 설정
   * @param {Function}   options.onIndexChange - 인덱스 변경 시 콜백
   */
  constructor(sentences, tts, options = {}) {
    this.sentences   = sentences || [];
    this.tts         = tts;
    this.currentIdx  = 0; // 현재 표시 중인 문장 인덱스
    this.options     = options;

    // DOM 요소 참조 (초기화 후 _bindDOM()에서 설정)
    this.els = {};

    // 초기화
    this._bindDOM();
    this._bindEvents();
    this._render(); // 첫 번째 문장 표시
  }

  /**
   * 필요한 DOM 요소들을 찾아 저장한다.
   * @private
   */
  _bindDOM() {
    this.els = {
      // 메인 문장 카드 (탭하면 다음으로)
      card:           document.getElementById('sentence-card'),
      // 영어 문장 텍스트
      enText:         document.getElementById('sentence-en'),
      // 한국어 문장 텍스트
      koText:         document.getElementById('sentence-ko'),
      // 진행 카운터 (예: "3 / 10")
      progressCount:  document.getElementById('progress-count'),
      // 진행 퍼센트 (예: "30%")
      progressPct:    document.getElementById('progress-percent'),
      // 진행 바 채우기
      progressFill:   document.getElementById('progress-fill'),
      // 이전 버튼
      prevBtn:        document.getElementById('prev-btn'),
      // 다음 버튼
      nextBtn:        document.getElementById('next-btn'),
      // TTS 재생 버튼
      playBtn:        document.getElementById('tts-play-btn'),
      // 목차 버튼
      tocBtn:         document.getElementById('toc-btn'),
      // 목차 모달 오버레이
      tocModal:       document.getElementById('toc-modal'),
      // 목차 닫기 버튼
      tocCloseBtn:    document.getElementById('toc-close-btn'),
      // 목차 리스트
      tocList:        document.getElementById('toc-list'),
    };
  }

  /**
   * 이벤트 리스너를 등록한다.
   * @private
   */
  _bindEvents() {
    // 문장 카드 탭 → 다음 문장으로 이동 후 그 문장을 TTS로 재생
    // (업데이트 v3: 이동 전에 먼저 재생하면 방금 지나간 이전 문장이 읽혀서
    //  "다음 버튼을 눌렀는데 이전 문장이 재생되는" 오류가 발생했음 → 순서 반전)
    if (this.els.card) {
      this.els.card.addEventListener('click', () => {
        this.next();
        this._speakCurrent();
      });
    }

    // 이전 버튼 → 이전 문장으로 이동 후 그 문장을 TTS로 재생
    if (this.els.prevBtn) {
      this.els.prevBtn.addEventListener('click', (e) => {
        e.stopPropagation(); // 카드 클릭 이벤트 차단
        this.prev();
        this._speakCurrent();
      });
    }

    // 다음 버튼 → 다음 문장으로 이동 후 그 문장을 TTS로 재생
    if (this.els.nextBtn) {
      this.els.nextBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.next();
        this._speakCurrent();
      });
    }

    // TTS 재생 버튼 (재생/중지 토글)
    if (this.els.playBtn) {
      this.els.playBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (this.tts.playing) {
          this.tts.stop();
          this._updatePlayBtn(false);
        } else {
          this._speakCurrent();
        }
      });
    }

    // 목차 버튼 → 모달 열기
    if (this.els.tocBtn) {
      this.els.tocBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._openTOC();
      });
    }

    // 목차 모달 닫기
    if (this.els.tocCloseBtn) {
      this.els.tocCloseBtn.addEventListener('click', () => this._closeTOC());
    }

    // 모달 오버레이 클릭 → 닫기
    if (this.els.tocModal) {
      this.els.tocModal.addEventListener('click', (e) => {
        if (e.target === this.els.tocModal) this._closeTOC();
      });
    }

    // TTS 재생 종료 → 버튼 상태 업데이트
    if (this.tts) {
      this.tts.onStart = () => this._updatePlayBtn(true);
      this.tts.onEnd   = () => this._updatePlayBtn(false);
    }

    // 키보드 단축키 (데스크탑 지원)
    document.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowRight' || e.key === ' ') {
        e.preventDefault();
        this.next();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        this.prev();
      } else if (e.key === 'Enter') {
        this._speakCurrent();
      }
    });
  }

  /**
   * 현재 문장을 화면에 렌더링한다.
   * @private
   */
  _render() {
    if (this.sentences.length === 0) return;

    const sentence = this.sentences[this.currentIdx];
    const total    = this.sentences.length;
    const current  = this.currentIdx + 1;
    const pct      = Math.round((current / total) * 100);

    // 텍스트 업데이트 (애니메이션을 위해 잠깐 제거 후 추가)
    if (this.els.enText) {
      this.els.enText.style.animation = 'none';
      // eslint-disable-next-line no-unused-expressions
      this.els.enText.offsetHeight; // 리플로우 강제 (애니메이션 재시작용)
      this.els.enText.style.animation = '';
      this.els.enText.innerHTML = sentence.en; // HTML 그대로 (bold 지원)
    }

    if (this.els.koText) {
      this.els.koText.style.animation = 'none';
      // eslint-disable-next-line no-unused-expressions
      this.els.koText.offsetHeight;
      this.els.koText.style.animation = '';
      this.els.koText.textContent = sentence.ko;
    }

    // 진행 상황 업데이트
    if (this.els.progressCount) {
      this.els.progressCount.textContent = `${current} / ${total}`;
    }
    if (this.els.progressPct) {
      this.els.progressPct.textContent = `${pct}%`;
    }
    if (this.els.progressFill) {
      this.els.progressFill.style.width = `${pct}%`;
    }

    // 버튼 비활성화 처리 (첫/마지막 문장)
    if (this.els.prevBtn) {
      this.els.prevBtn.disabled = (this.currentIdx === 0);
    }
    if (this.els.nextBtn) {
      this.els.nextBtn.disabled = (this.currentIdx === total - 1);
    }

    // 외부 콜백 호출
    if (typeof this.options.onIndexChange === 'function') {
      this.options.onIndexChange(this.currentIdx);
    }

    // 목차 현재 위치 하이라이트 업데이트
    this._updateTOCHighlight();
  }

  /**
   * 현재 문장의 영어 텍스트를 TTS로 읽는다.
   * @private
   */
  _speakCurrent() {
    if (!this.tts || this.sentences.length === 0) return;
    const sentence = this.sentences[this.currentIdx];
    this.tts.speak(sentence.en);
  }

  /**
   * TTS 재생 버튼 UI를 업데이트한다.
   * @param {boolean} playing - 재생 중 여부
   * @private
   */
  _updatePlayBtn(playing) {
    if (!this.els.playBtn) return;
    if (playing) {
      this.els.playBtn.classList.add('playing');
      this.els.playBtn.textContent = '⏸';
    } else {
      this.els.playBtn.classList.remove('playing');
      this.els.playBtn.textContent = '▶';
    }
  }

  /**
   * 다음 문장으로 이동한다.
   * 마지막 문장이면 이동하지 않는다.
   */
  next() {
    if (this.currentIdx < this.sentences.length - 1) {
      this.tts && this.tts.stop();
      this.currentIdx++;
      this._render();
    }
  }

  /**
   * 이전 문장으로 이동한다.
   * 첫 번째 문장이면 이동하지 않는다.
   */
  prev() {
    if (this.currentIdx > 0) {
      this.tts && this.tts.stop();
      this.currentIdx--;
      this._render();
    }
  }

  /**
   * 특정 인덱스의 문장으로 바로 이동한다.
   * @param {number} idx - 이동할 인덱스
   */
  goTo(idx) {
    if (idx >= 0 && idx < this.sentences.length) {
      this.tts && this.tts.stop();
      this.currentIdx = idx;
      this._render();
      this._closeTOC();
    }
  }

  /**
   * 목차 모달을 열고 전체 문장 리스트를 표시한다.
   * @private
   */
  _openTOC() {
    if (!this.els.tocModal || !this.els.tocList) return;

    // 목차 리스트 생성
    this.els.tocList.innerHTML = '';
    this.sentences.forEach((s, idx) => {
      const item = document.createElement('div');
      item.className = `toc-item${idx === this.currentIdx ? ' current' : ''}`;
      item.dataset.idx = idx;
      item.innerHTML = `
        <div class="toc-item-num">${idx + 1}번</div>
        <div class="toc-item-en">${s.en}</div>
        <div class="toc-item-ko">${s.ko}</div>
      `;

      // 탭하면 해당 문장으로 이동
      item.addEventListener('click', () => this.goTo(idx));
      this.els.tocList.appendChild(item);
    });

    // 현재 문장으로 스크롤
    const currentItem = this.els.tocList.querySelector('.current');
    if (currentItem) {
      setTimeout(() => currentItem.scrollIntoView({ block: 'center' }), 100);
    }

    // 모달 열기 (애니메이션)
    this.els.tocModal.classList.add('open');
  }

  /**
   * 목차 모달을 닫는다.
   * @private
   */
  _closeTOC() {
    if (this.els.tocModal) {
      this.els.tocModal.classList.remove('open');
    }
  }

  /**
   * 목차 모달에서 현재 문장 하이라이트를 업데이트한다.
   * @private
   */
  _updateTOCHighlight() {
    if (!this.els.tocList) return;
    const items = this.els.tocList.querySelectorAll('.toc-item');
    items.forEach((item, idx) => {
      item.classList.toggle('current', idx === this.currentIdx);
    });
  }
}
