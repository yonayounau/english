/* ============================================================
   main.js - 앱 공통 초기화 및 유틸리티
   ============================================================ */

// ============================================================
// 토스트 알림 유틸리티
// ============================================================

/**
 * 하단에 잠깐 나타났다 사라지는 토스트 메시지를 표시한다.
 * @param {string}  message - 표시할 메시지
 * @param {number}  duration - 표시 시간 (ms, 기본 2500)
 */
function showToast(message, duration = 2500) {
  // 기존 토스트가 있으면 제거
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  document.body.appendChild(toast);

  // 다음 프레임에서 show 클래스 추가 (CSS transition 동작)
  requestAnimationFrame(() => {
    requestAnimationFrame(() => toast.classList.add('show'));
  });

  // 지정 시간 후 사라지기
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}


// ============================================================
// 속도 조절 UI 초기화
// ============================================================

/**
 * 속도 조절 버튼 (+/-) 이벤트를 등록하고 UI를 업데이트한다.
 * @param {TTSControl} tts      - TTSControl 인스턴스
 * @param {string} displayId    - 속도 표시 요소 ID (기본: 'speed-value')
 */
function initSpeedControl(tts, displayId = 'speed-value') {
  const speedDisplay  = document.getElementById(displayId);
  const speedUpBtn    = document.getElementById('speed-up');
  const speedDownBtn  = document.getElementById('speed-down');

  // 현재 속도 화면에 표시
  const updateDisplay = () => {
    if (speedDisplay) {
      speedDisplay.textContent = `${tts.rate.toFixed(2)}x`;
    }
  };

  updateDisplay(); // 초기 표시

  // 속도 올리기 버튼
  if (speedUpBtn) {
    speedUpBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const newRate = tts.increaseRate();
      updateDisplay();
      showToast(`재생 속도: ${newRate.toFixed(2)}배속`);

      // 현재 재생 중이면 새 속도로 재시작
      if (tts.playing) {
        const currentText = document.getElementById('sentence-en')?.innerText;
        if (currentText) tts.speak(currentText);
      }
    });
  }

  // 속도 내리기 버튼
  if (speedDownBtn) {
    speedDownBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const newRate = tts.decreaseRate();
      updateDisplay();
      showToast(`재생 속도: ${newRate.toFixed(2)}배속`);
    });
  }
}


// ============================================================
// Notion 동기화 버튼 처리
// ============================================================

/**
 * Notion 동기화 버튼에 이벤트를 등록한다.
 * 서버의 /api/sync 엔드포인트를 호출한다.
 */
function initSyncButton() {
  const syncBtn = document.getElementById('sync-btn');
  if (!syncBtn) return;

  syncBtn.addEventListener('click', async () => {
    // 로딩 상태 표시
    syncBtn.classList.add('syncing');
    syncBtn.disabled = true;
    const originalText = syncBtn.querySelector('.sync-text')?.textContent;
    if (syncBtn.querySelector('.sync-text')) {
      syncBtn.querySelector('.sync-text').textContent = '동기화 중...';
    }

    try {
      const response = await fetch('/api/sync', { method: 'POST' });
      const data     = await response.json();

      if (data.success) {
        showToast('✅ Notion 동기화 완료! 페이지를 새로고침합니다.');
        // 2초 후 새로고침 (새 데이터 반영)
        setTimeout(() => window.location.reload(), 2000);
      } else {
        showToast(`❌ 동기화 실패: ${data.message}`);
      }
    } catch (err) {
      console.error('[동기화 오류]', err);
      showToast('❌ 서버 연결에 실패했습니다.');
    } finally {
      // 로딩 상태 해제
      syncBtn.classList.remove('syncing');
      syncBtn.disabled = false;
      if (syncBtn.querySelector('.sync-text') && originalText) {
        syncBtn.querySelector('.sync-text').textContent = originalText;
      }
    }
  });
}


// ============================================================
// 뒤로가기 버튼 처리
// ============================================================

/**
 * 헤더의 뒤로가기 버튼에 이벤트를 등록한다.
 */
function initBackButton() {
  const backBtn = document.querySelector('.header-back-btn');
  if (!backBtn) return;

  backBtn.addEventListener('click', () => {
    // 히스토리가 있으면 뒤로, 없으면 홈으로
    if (window.history.length > 1) {
      window.history.back();
    } else {
      window.location.href = '/';
    }
  });
}


// ============================================================
// 현재 페이지 네비게이션 활성화
// ============================================================

/**
 * 현재 URL 경로에 맞게 하단 네비 아이템을 활성화한다.
 */
function updateNavActive() {
  const path    = window.location.pathname;
  const navItems = document.querySelectorAll('.nav-item');

  navItems.forEach(item => {
    const href = item.getAttribute('href') || '';
    item.classList.remove('active');

    // 경로 매칭 (완전 일치 또는 접두사 일치)
    if (href === '/' && path === '/') {
      item.classList.add('active');
    } else if (href !== '/' && path.startsWith(href)) {
      item.classList.add('active');
    }
  });
}


// ============================================================
// 앱 초기화 (DOM 로드 후 실행)
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  // 공통 기능 초기화
  initBackButton();
  initSyncButton();
  updateNavActive();

  // iOS Safari 스크롤 부드럽게 처리
  document.documentElement.style.scrollBehavior = 'smooth';

  console.log('[앱] 빨모쌤 영어공부 앱 초기화 완료');
});
