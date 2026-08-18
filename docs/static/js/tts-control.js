/* ============================================================
   tts-control.js - TTS(텍스트 음성 변환) 컨트롤 모듈
   Web Speech API (SpeechSynthesis) 기반
   
   크롬 브라우저에서 가장 좋은 음질의 en-US 음성을 자동 선택한다.
   ============================================================ */

/**
 * TTSControl 클래스
 * 텍스트 읽기(TTS) 기능을 담당하는 모듈
 * 
 * 사용법:
 *   const tts = new TTSControl();
 *   tts.speak("Hello, how are you?");
 *   tts.setRate(1.5);
 *   tts.stop();
 */
class TTSControl {
  constructor() {
    // Web Speech API 지원 여부 확인
    if (!('speechSynthesis' in window)) {
      console.warn('[TTS] 이 브라우저는 Web Speech API를 지원하지 않습니다.');
      this.supported = false;
      return;
    }

    this.supported = true;
    this.synth     = window.speechSynthesis;
    this.rate      = 1.0;    // 기본 재생 속도
    this.pitch     = 1.0;    // 음정 (1.0 = 기본값)
    this.volume    = 1.0;    // 볼륨 (0~1)
    this.voice     = null;   // 선택된 음성 (null이면 브라우저 기본)
    this.isPlaying = false;  // 현재 재생 중 여부

    // 콜백 함수 (외부에서 재생 상태 감지용)
    this.onStart   = null;   // 재생 시작 시 호출
    this.onEnd     = null;   // 재생 종료 시 호출
    this.onError   = null;   // 에러 발생 시 호출

    // 음성 목록 로드 (브라우저에 따라 비동기)
    this._loadVoices();
  }

  /**
   * 최고 품질의 영어(en-US) 음성을 찾아 선택한다.
   * 크롬의 경우 'Google US English' 또는 'Google UK English' 음성이 최고 품질.
   * 없으면 en-US 계열 음성 중 첫 번째를 사용한다.
   * @private
   */
  _loadVoices() {
    const setVoice = () => {
      const voices = this.synth.getVoices();
      if (voices.length === 0) return; // 아직 로드 안 됨

      // 우선순위: Google Neural 음성 > Google 음성 > en-US 음성 > en 음성
      const priorityNames = [
        'Google US English',
        'Google UK English Female',
        'Google UK English Male',
        'Microsoft Aria Online (Natural) - English (United States)',
        'Microsoft Guy Online (Natural) - English (United States)',
        'Samantha',     // macOS/iOS 음성
        'Alex',         // macOS 음성
      ];

      // 우선순위 목록에서 순서대로 찾기
      for (const name of priorityNames) {
        const v = voices.find(v => v.name === name);
        if (v) {
          this.voice = v;
          console.log(`[TTS] 음성 선택: ${v.name} (${v.lang})`);
          return;
        }
      }

      // 우선순위 없으면 en-US 계열 중 첫 번째 선택
      const enUS = voices.find(v => v.lang === 'en-US');
      if (enUS) {
        this.voice = enUS;
        console.log(`[TTS] 음성 선택 (en-US 기본): ${enUS.name}`);
        return;
      }

      // 그래도 없으면 영어 계열 아무거나
      const en = voices.find(v => v.lang.startsWith('en'));
      if (en) {
        this.voice = en;
        console.log(`[TTS] 음성 선택 (en 기본): ${en.name}`);
      }
    };

    // 음성 목록이 이미 있으면 즉시 설정
    setVoice();

    // Chrome은 voiceschanged 이벤트 발생 후 사용 가능
    this.synth.addEventListener('voiceschanged', setVoice);
  }

  /**
   * TTS로 읽기 전에 텍스트를 정리한다.
   * - HTML 태그 제거 (예: <strong>word</strong> → word)
   * - 화자 표시(A:, B:, C:), 번호(1. / 2)), 특수기호(→, -, • 등) 접두어는
   *   실제 문장 내용이 아니므로 읽지 않고 제거한다. (업데이트 v3)
   *
   * @param {string} text - 원본 텍스트
   * @returns {string} TTS로 읽을 순수 텍스트
   * @private
   */
  _prepareForSpeech(text) {
    let plain = text.replace(/<[^>]+>/g, '').trim();
    if (!plain) return '';

    const leadingPatterns = [
      /^[A-Za-z]\s*[:：]\s*/,          // 화자 표시: A: , B: , C:
      /^\d+\s*[.)\]:：]\s*/,           // 번호: 1. , 2) , 3:
      /^[→➡▶◀▷◁\-–—•*✓✔○●□■♦♣]+\s*/, // 특수기호: → - • 등
    ];

    // 여러 접두어가 겹쳐 있을 수 있으므로(예: "1. A: ...") 더 이상 지워질 게
    // 없을 때까지 반복해서 제거한다.
    let changed = true;
    while (changed) {
      changed = false;
      for (const pattern of leadingPatterns) {
        const stripped = plain.replace(pattern, '');
        if (stripped !== plain) {
          plain = stripped;
          changed = true;
        }
      }
    }

    return plain.trim();
  }

  /**
   * 텍스트를 읽어준다.
   * 이미 재생 중이면 먼저 중지하고 새로 시작한다.
   *
   * @param {string} text - 읽을 텍스트 (HTML 태그·화자 표시·번호·특수기호 자동 제거)
   */
  speak(text) {
    if (!this.supported) return;

    const plainText = this._prepareForSpeech(text);
    if (!plainText) return;

    // 이전 재생 중지
    this.stop();

    // SpeechSynthesisUtterance 생성
    const utterance = new SpeechSynthesisUtterance(plainText);

    // 음성 설정
    if (this.voice) {
      utterance.voice = this.voice;
    }
    utterance.rate   = this.rate;
    utterance.pitch  = this.pitch;
    utterance.volume = this.volume;
    utterance.lang   = 'en-US';

    // 이벤트 핸들러 설정
    utterance.onstart = () => {
      this.isPlaying = true;
      if (typeof this.onStart === 'function') this.onStart();
    };

    utterance.onend = () => {
      this.isPlaying = false;
      if (typeof this.onEnd === 'function') this.onEnd();
    };

    utterance.onerror = (e) => {
      this.isPlaying = false;
      // 'interrupted' 에러는 정상 중단으로 무시
      if (e.error === 'interrupted') return;
      console.warn('[TTS] 에러:', e.error);
      if (typeof this.onError === 'function') this.onError(e);
    };

    // 재생 시작
    this.synth.speak(utterance);
  }

  /**
   * 현재 재생을 즉시 중지한다.
   */
  stop() {
    if (!this.supported) return;
    if (this.synth.speaking || this.synth.pending) {
      this.synth.cancel();
    }
    this.isPlaying = false;
  }

  /**
   * 재생 속도를 설정한다.
   * @param {number} rate - 속도 (0.5 ~ 2.0)
   */
  setRate(rate) {
    // 범위 제한 (0.5 ~ 2.0)
    this.rate = Math.min(2.0, Math.max(0.5, rate));
  }

  /**
   * 속도를 한 단계 올린다 (+0.25).
   * 최대 2.0배속까지.
   * @returns {number} 변경 후 속도
   */
  increaseRate() {
    this.setRate(Math.round((this.rate + 0.25) * 100) / 100);
    return this.rate;
  }

  /**
   * 속도를 한 단계 낮춘다 (-0.25).
   * 최소 0.5배속까지.
   * @returns {number} 변경 후 속도
   */
  decreaseRate() {
    this.setRate(Math.round((this.rate - 0.25) * 100) / 100);
    return this.rate;
  }

  /**
   * 현재 재생 중인지 여부를 반환한다.
   * @returns {boolean}
   */
  get playing() {
    return this.synth.speaking;
  }

  /**
   * 사용 가능한 영어 음성 목록을 반환한다 (디버깅용).
   * @returns {SpeechSynthesisVoice[]}
   */
  getEnglishVoices() {
    return this.synth.getVoices().filter(v => v.lang.startsWith('en'));
  }
}

// 전역 TTS 인스턴스 생성 (싱글톤 패턴)
const ttsControl = new TTSControl();
