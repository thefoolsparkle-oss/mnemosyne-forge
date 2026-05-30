/**
 * Mnemosyne Forge — Frontend Application
 * Handles session lifecycle, chat UI, draft panel updates, and export.
 */

(function () {
  'use strict';

  // ─── State ────────────────────────────────────────────
  const state = {
    sessionId: null,
    draft: null,
    isLoading: false,
  };

  // ─── DOM refs ────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const welcomeScreen = $('#welcome-screen');
  const workspace = $('#workspace');
  const initialIdea = $('#initial-idea');
  const btnStart = $('#btn-start');
  const welcomeError = $('#welcome-error');
  const chatMessages = $('#chat-messages');
  const chatInput = $('#chat-input');
  const btnSend = $('#btn-send');
  const btnSearch = $('#btn-search');
  const searchPanel = $('#search-overlay');
  const searchInput = $('#search-input');
  const btnSearchGo = $('#btn-search-go');
  const btnSearchClose = $('#btn-search-close');
  const searchResult = $('#search-result');
  const searchHistory = $('#search-history');
  const btnNewSession = $('#btn-new-session');
  const btnExport = $('#btn-export');
  const exportStatus = $('#export-status');
  const toast = $('#toast');
  const cardOverlay = $('#card-overlay');
  const cardName = $('#card-name');
  const cardTags = $('#card-tags');
  const cardDescription = $('#card-description');
  const cardPersonality = $('#card-personality');
  const cardScenario = $('#card-scenario');
  const cardFirstMes = $('#card-first-mes');
  const cardMesExample = $('#card-mes-example');
  const btnCloseCard = $('#btn-close-card');
  const btnDownloadV2 = $('#btn-download-v2');
  const btnBackChat = $('#btn-back-chat');
  const btnLibrary = $('#btn-library');
  const libraryOverlay = $('#library-overlay');
  const libraryList = $('#library-list');
  const btnCloseLibrary = $('#btn-close-library');
  const authOverlay = $('#auth-overlay');
  const btnLogin = $('#btn-login');
  const btnCloseAuth = $('#btn-close-auth');
  const authError = $('#auth-error');
  const userStatus = $('#user-status');
  const btnDashNew = $('#btn-dash-new');
  const btnBackDash = $('#btn-back-dash');
  const dashboard = $('#dashboard');

  // ─── Toast ───────────────────────────────────────────
  let toastTimer = null;

  function showToast(message, type) {
    if (toastTimer) clearTimeout(toastTimer);
    toast.textContent = message;
    toast.className = 'toast ' + type + ' show';
    toastTimer = setTimeout(() => {
      toast.classList.remove('show');
      toastTimer = null;
    }, 3500);
  }

  // ─── Error display ───────────────────────────────────
  function showError(el, message) {
    el.textContent = message;
    el.classList.remove('hidden');
  }

  function hideError(el) {
    el.textContent = '';
    el.classList.add('hidden');
  }

  // ─── API helpers ─────────────────────────────────────
  async function apiCall(method, url, body) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body) opts.body = JSON.stringify(body);

    let resp;
    try {
      resp = await fetch(url, opts);
    } catch (e) {
      throw new Error('无法连接服务器，请确认后端已启动 (http://127.0.0.1:8010)');
    }

    if (!resp.ok) {
      if (resp.status === 500) throw new Error('服务器内部错误，请查看终端日志');
      if (resp.status === 404) throw new Error('会话不存在或已过期');
      throw new Error('请求失败 (' + resp.status + ')');
    }

    const data = await resp.json();

    if (data.ok === false) {
      throw new Error(data.error || data.detail || '请求失败');
    }

    return data;
  }

  // ─── Markdown rendering (basic) ──────────────────────
  function renderMarkdown(text) {
    if (!text) return '';
    let html = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Numbered lists: detect lines starting with number + dot
    html = html.replace(/(?:^|\n)(\d+)\. (.+?)(?=\n|$)/g, function (m, num, content) {
      return '\n<li>' + num + '. ' + content + '</li>';
    });

    // Wrap consecutive <li> in <ol>
    html = html.replace(/((?:<li>.*?<\/li>\n?)+)/g, function (m) {
      return '<ol>' + m + '</ol>';
    });

    // Line breaks
    html = html.replace(/\n\n/g, '<br><br>');
    html = html.replace(/\n/g, '<br>');

    return html;
  }

  // ─── Chat rendering ──────────────────────────────────
  function addMessage(role, content, timestamp) {
    const div = document.createElement('div');
    div.className = 'msg ' + role;

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.innerHTML = renderMarkdown(content);
    div.appendChild(bubble);

    const time = document.createElement('div');
    time.className = 'msg-time';
    time.textContent = timestamp || new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    div.appendChild(time);

    chatMessages.appendChild(div);
    scrollToBottom();
  }

  function addThinkingMessage() {
    const div = document.createElement('div');
    div.className = 'msg assistant thinking';
    div.id = 'thinking-msg';

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.innerHTML = '思考中<span class="dots"><span>.</span><span>.</span><span>.</span></span>';
    div.appendChild(bubble);

    chatMessages.appendChild(div);
    scrollToBottom();
  }

  function removeThinkingMessage() {
    const el = document.getElementById('thinking-msg');
    if (el) el.remove();
  }

  function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  // ─── Draft panel update ──────────────────────────────
  const STAGE_LABELS = {
    core_concept: '核心概念',
    personality: '性格塑造',
    appearance: '外貌描述',
    background: '背景故事',
    abilities: '能力设定',
    relationships: '人际关系',
    speaking_style: '说话方式',
    scenario: '使用场景',
    opening: '开场设计',
    final_review: '最终确认',
  };

  const FIELD_LABELS = {
    name: '名字',
    core_concept: '核心概念',
    personality: '性格',
    appearance: '外貌',
    background: '背景',
    speaking_style: '说话方式',
    scenario: '使用场景',
    abilities: '能力',
    weaknesses: '弱点',
    relationships: '关系',
    first_message: '开场白',
    example_dialogue: '示例对话',
  };

  function updateDraftPanel(draft) {
    state.draft = draft;

    // Update field values
    $$('.draft-field').forEach(function (el) {
      const field = el.dataset.field;
      const valueEl = el.querySelector('.field-value');
      if (!field || !valueEl) return;

      const val = draft[field];

      if (field === 'personality' || field === 'abilities' || field === 'weaknesses' || field === 'relationships' || field === 'themes' || field === 'tags') {
        if (Array.isArray(val) && val.length > 0) {
          valueEl.textContent = val.join('、');
          valueEl.classList.remove('empty');
        } else {
          valueEl.textContent = '待补充';
          valueEl.classList.add('empty');
        }
      } else if (val && typeof val === 'string' && val.trim()) {
        valueEl.textContent = val.length > 80 ? val.slice(0, 80) + '...' : val;
        valueEl.classList.remove('empty');
      } else if (val && typeof val === 'number') {
        valueEl.textContent = String(val);
        valueEl.classList.remove('empty');
      } else {
        valueEl.textContent = '待补充';
        valueEl.classList.add('empty');
      }

      // Locked indicator
      if (draft.locked_fields && draft.locked_fields.includes(field)) {
        el.classList.add('locked');
      } else {
        el.classList.remove('locked');
      }

      // Make editable on click
      if (!el._editBound) {
        el._editBound = true;
        el.addEventListener('click', function(e) {
          if (el.querySelector('input, textarea')) return;
          var valEl = el.querySelector('.field-value');
          var currentVal = draft[field];
          var isList = ['personality','abilities','weaknesses','relationships','themes','tags'].includes(field);

          var input = document.createElement(isList ? 'input' : 'textarea');
          input.className = 'field-edit';
          if (isList) {
            input.value = Array.isArray(currentVal) ? currentVal.join('、') : '';
            input.placeholder = '用顿号分隔';
          } else {
            input.value = (typeof currentVal === 'string') ? currentVal : '';
            input.placeholder = '输入内容……';
            input.rows = 3;
          }
          valEl.replaceWith(input);
          input.focus();

          async function saveEdit() {
            var newVal = input.value.trim();
            var update = {};
            if (isList) {
              update[field] = newVal ? newVal.split(/[、,，]/).map(function(s) { return s.trim(); }).filter(Boolean) : [];
            } else {
              update[field] = newVal || null;
            }

            try {
              var data = await apiCall('PATCH', '/api/sessions/' + state.sessionId + '/draft', { updates: update });
              if (data.draft) updateDraftPanel(data.draft);
              showToast('已保存', 'success');
            } catch (e) {
              showToast('保存失败: ' + e.message, 'error');
              updateDraftPanel(state.draft); // revert
            }
          }

          input.addEventListener('blur', saveEdit);
          input.addEventListener('keydown', function(ev) {
            if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); input.blur(); }
            if (ev.key === 'Escape') { updateDraftPanel(state.draft); }
          });
        });
      }
    });

    // Completion score
    const score = draft.completion_score || 0;
    const pct = Math.round(score * 100);
    var coreFields = ['name','core_concept','personality','appearance','background'];
    var filled = coreFields.filter(function(f) { return draft[f] && (typeof draft[f] !== 'object' || draft[f].length > 0); }).length;
    $('#completion-detail').textContent = '核心字段 ' + filled + '/' + coreFields.length;
    $('#completion-percent').textContent = pct + '%';
    $('#progress-fill').style.width = pct + '%';

    // Update draft panel title to show character name
    var draftTitle = draft.name || draft.core_concept;
    $('.draft-title').textContent = draftTitle ? '角色 · ' + draftTitle.slice(0, 15) : '角色草稿';

    // Current stage
    const stage = draft.current_stage || 'core_concept';
    $('#current-stage').textContent = STAGE_LABELS[stage] || stage;
  }

  // ─── Session lifecycle ───────────────────────────────
  async function createSession(idea, fastMode) {
    hideError(welcomeError);
    setLoading(true, fastMode ? $('#btn-fast') : btnStart, fastMode ? '生成中……' : '创建中……');

    try {
      const data = await apiCall('POST', '/api/sessions', { initial_idea: idea, fast_mode: fastMode });
      state.sessionId = data.session_id;

      // Transition to workspace
      dashboard.classList.add('hidden');
      welcomeScreen.classList.add('hidden');
      workspace.classList.remove('hidden');
      btnBackDash.classList.remove('hidden');
      chatMessages.innerHTML = '';

      // Add initial messages
      addMessage('user', idea);
      addMessage('assistant', data.assistant_message);

      // Update draft
      if (data.draft) updateDraftPanel(data.draft);

      // Show card preview in fast mode
      if (data.card) showCardPreview(data.card);

    } catch (e) {
      showError(welcomeError, e.message);
    } finally {
      var restoreBtn = fastMode ? $('#btn-fast') : btnStart;
      var restoreText = fastMode ? '⚡ 一键生成角色卡' : '开始创作 · 逐步引导';
      setLoading(false, restoreBtn, restoreText);
    }
  }

  async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message || state.isLoading || !state.sessionId) return;

    chatInput.value = '';
    hideError(exportStatus);
    setLoading(true, btnSend, '发送中……');
    addMessage('user', message);
    addThinkingMessage();

    try {
      const data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/messages', { message: message });

      removeThinkingMessage();
      addMessage('assistant', data.assistant_message);

      if (data.draft) updateDraftPanel(data.draft);
      if (data.card) showCardPreview(data.card);

    } catch (e) {
      removeThinkingMessage();
      showToast(e.message, 'error');
    } finally {
      setLoading(false, btnSend, '发送');
      chatInput.focus();
    }
  }

  async function exportCard() {
    if (!state.sessionId) return;

    setLoading(true, btnExport, '导出中……');
    hideError(exportStatus);

    try {
      const data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/export/card-v2');

      if (data.ok) {
        exportStatus.textContent = '';
        exportStatus.className = 'export-status';
        exportStatus.classList.add('hidden');
        showCardPreview(data.card);
      } else {
        throw new Error(data.error || '导出失败');
      }
    } catch (e) {
      exportStatus.textContent = e.message;
      exportStatus.className = 'export-status error';
      exportStatus.classList.remove('hidden');
      showToast(e.message, 'error');
    } finally {
      setLoading(false, btnExport, '导出角色卡 V2');
    }
  }

  // ─── Card Preview ────────────────────────────────────
  function showCardPreview(card) {
    var data = card.data || card;
    cardName.textContent = data.name || '未命名';
    cardTags.innerHTML = (data.tags || []).map(function(t) { return '<span class="card-tag">' + t + '</span>'; }).join('');
    cardDescription.textContent = data.description || '';
    cardPersonality.textContent = data.personality || '';
    cardScenario.textContent = data.scenario || '';
    cardFirstMes.textContent = data.first_mes || '';
    cardMesExample.textContent = data.mes_example || '';

    var greetings = $('#card-greetings');
    var greetsSection = $('#card-greetings-section');
    if (data.alternate_greetings && data.alternate_greetings.length > 0) {
      greetings.innerHTML = data.alternate_greetings.map(function(g) { return '<p class="card-quote">' + g + '</p>'; }).join('');
      greetsSection.classList.remove('hidden');
    } else {
      greetsSection.classList.add('hidden');
    }

    var notesSection = $('#card-notes-section');
    if (data.creator_notes) {
      $('#card-creator-notes').textContent = data.creator_notes;
      notesSection.classList.remove('hidden');
    } else {
      notesSection.classList.add('hidden');
    }

    cardOverlay.classList.remove('hidden');
  }

  function hideCardPreview() {
    cardOverlay.classList.add('hidden');
  }

  function downloadCard() {
    if (!state.sessionId) return;
    var a = document.createElement('a');
    a.href = '/api/sessions/' + state.sessionId + '/export/download';
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  btnCloseCard.addEventListener('click', hideCardPreview);
  btnBackChat.addEventListener('click', hideCardPreview);
  btnDownloadV2.addEventListener('click', downloadCard);

  cardOverlay.addEventListener('click', function(e) {
    if (e.target === cardOverlay) hideCardPreview();
  });

  function resetToWelcome() {
    state.sessionId = null;
    state.draft = null;
    welcomeScreen.classList.remove('hidden');
    workspace.classList.add('hidden');
    dashboard.classList.add('hidden');
    cardOverlay.classList.add('hidden');
    chatMessages.innerHTML = '';
    chatInput.value = '';
    initialIdea.value = '';
    hideError(welcomeError);
    hideError(exportStatus);
    exportStatus.classList.add('hidden');
  }

  // ─── Character Library ───────────────────────────────
  async function loadLibrary() {
    try {
      var data = await apiCall('GET', '/api/sessions');
      var sessions = data.sessions || [];
      libraryList.innerHTML = '';

      if (sessions.length === 0) {
        libraryList.innerHTML = '<div class="library-empty">还没有创建过角色<br>去首页开始创作吧</div>';
        btnLibrary.textContent = '角色库';
        return;
      }

      sessions.forEach(function(s) {
        var div = document.createElement('div');
        div.className = 'library-item';
        div.dataset.sessionId = s.id;
        var name = s.title || '未命名';
        var concept = s.core_concept || '';
        var score = Math.round((s.completion_score || 0) * 100);
        var date = new Date(s.updated_at).toLocaleDateString('zh-CN');

        div.innerHTML =
          '<div class="library-item-avatar">' + (name[0] || '?') + '</div>' +
          '<div class="library-item-info">' +
            '<div class="library-item-name">' + name + '</div>' +
            '<div class="library-item-concept">' + (concept || '无描述') + '</div>' +
          '</div>' +
          '<div class="library-item-meta">' +
            '<div class="library-item-score">' + score + '%</div>' +
            '<div class="library-item-date">' + date + '</div>' +
          '</div>' +
          '<button class="library-item-del" data-sid="' + s.id + '">&times;</button>';

        div.querySelector('.library-item-del').addEventListener('click', function(e) {
          e.stopPropagation();
          deleteSession(s.id, name);
        });
        div.addEventListener('click', function() { resumeSession(s.id); });
        libraryList.appendChild(div);
      });

      btnLibrary.textContent = '角色库 (' + sessions.length + ')';
    } catch (e) {
      libraryList.innerHTML = '<div class="library-empty">加载失败：' + e.message + '</div>';
      btnLibrary.textContent = '角色库';
    }
  }

  async function resumeSession(sessionId) {
    try {
      setLoading(true, btnStart, '加载中……');
      var data = await apiCall('GET', '/api/sessions/' + sessionId + '/resume');
      state.sessionId = data.session_id;

      // Hide library + dashboard + welcome, show workspace
      libraryOverlay.classList.add('hidden');
      dashboard.classList.add('hidden');
      welcomeScreen.classList.add('hidden');
      workspace.classList.remove('hidden');
      btnBackDash.classList.remove('hidden');
      chatMessages.innerHTML = '';

      // Restore messages
      (data.messages || []).forEach(function(m) {
        addMessage(m.role, m.content, new Date(m.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }));
      });

      // Update draft
      if (data.draft) updateDraftPanel(data.draft);

      showToast('已恢复角色「' + (data.draft.name || data.draft.core_concept || '未命名') + '」', 'success');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false, btnStart, '开始创作');
    }
  }

  function showLibrary() {
    libraryOverlay.classList.remove('hidden');
    loadLibrary();
  }

  function hideLibrary() {
    libraryOverlay.classList.add('hidden');
  }

  async function deleteSession(sessionId, name) {
    if (!confirm('确定要删除「' + (name || '未命名') + '」吗？此操作不可恢复。')) return;
    try {
      await apiCall('DELETE', '/api/sessions/' + sessionId);
      showToast('已删除', 'success');
      loadLibrary();
      // If currently viewing this session, go back to dashboard
      if (state.sessionId === sessionId) {
        showDashboard();
      }
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  // ─── Dashboard ──────────────────────────────────────
  async function showDashboard() {
    welcomeScreen.classList.add('hidden');
    workspace.classList.add('hidden');
    cardOverlay.classList.add('hidden');
    dashboard.classList.remove('hidden');
    btnBackDash.classList.add('hidden');
  }

  // "New character" from dashboard
  btnDashNew.addEventListener('click', function() {
    dashboard.classList.add('hidden');
    welcomeScreen.classList.remove('hidden');
    btnBackDash.classList.remove('hidden');
    initialIdea.value = '';
    initialIdea.focus();
  });

  btnBackDash.addEventListener('click', function() {
    showDashboard();
  });

  // After creating session, stay in workspace - fast mode handled via parameter

  // ─── Loading state ───────────────────────────────────
  function setLoading(loading, btn, originalText) {
    state.isLoading = loading;
    btn.disabled = loading;
    if (loading) {
      btn.dataset.originalText = originalText || btn.textContent;
      btn.textContent = btn.dataset.originalText || '处理中……';
    } else {
      btn.textContent = originalText || btn.dataset.originalText || btn.textContent;
      btn.disabled = false;
    }
  }

  // ─── Event listeners ─────────────────────────────────

  // Start session - normal mode
  btnStart.addEventListener('click', function () {
    const idea = initialIdea.value.trim();
    if (!idea) { showError(welcomeError, '请输入角色灵感'); return; }
    createSession(idea, false);
  });

  // Fast mode
  $('#btn-fast').addEventListener('click', function () {
    const idea = initialIdea.value.trim();
    if (!idea) { showError(welcomeError, '请输入角色灵感'); return; }
    createSession(idea, true);
  });

  // Enter key on initial idea (Ctrl+Enter or just Enter)
  initialIdea.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      btnStart.click();
    }
  });

  // Send message
  btnSend.addEventListener('click', sendMessage);

  // Enter to send, Shift+Enter for newline
  chatInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // New session
  btnNewSession.addEventListener('click', function () {
    if (state.sessionId && state.draft && state.draft.completion_score > 0.1) {
      if (!confirm('确定要开始新角色吗？当前创作进度将丢失。')) return;
    }
    resetToWelcome();
    showDashboard();
  });

  // Export
  btnExport.addEventListener('click', exportCard);

  // Library
  btnLibrary.addEventListener('click', showLibrary);
  btnCloseLibrary.addEventListener('click', hideLibrary);
  libraryOverlay.addEventListener('click', function(e) {
    if (e.target === libraryOverlay) hideLibrary();
  });

  // Example tags
  $$('.example-tag').forEach(function (tag) {
    tag.addEventListener('click', function () {
      initialIdea.value = tag.dataset.idea;
      initialIdea.focus();
    });
  });

  // Auto-resize textareas
  [initialIdea, chatInput].forEach(function (ta) {
    ta.addEventListener('input', function () {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 150) + 'px';
    });
  });

  // ─── Search ──────────────────────────────────────────
  btnSearch.addEventListener('click', function() {
    searchPanel.classList.toggle('hidden');
    if (!searchPanel.classList.contains('hidden')) {
      searchInput.focus();
      loadSearchHistory();
    }
  });

  btnSearchClose.addEventListener('click', function() {
    searchPanel.classList.add('hidden');
  });

  searchPanel.addEventListener('click', function(e) {
    if (e.target === searchPanel) searchPanel.classList.add('hidden');
  });

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && !searchPanel.classList.contains('hidden')) {
      searchPanel.classList.add('hidden');
    }
  });

  searchPanel.addEventListener('click', function(e) {
    if (e.target === searchPanel) searchPanel.classList.add('hidden');
  });

  async function doSearch() {
    var q = searchInput.value.trim();
    if (!q || !state.sessionId) return;
    searchResult.innerHTML = '<div class="search-loading">搜索中……</div>';
    btnSearchGo.disabled = true;
    try {
      var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/search', { query: q, mode: 'manual' });
      if (data.ok && data.inspiration) {
        searchInput.value = '';
        renderInspirationCard(data.inspiration);
        loadSearchHistory();
      } else if (data.results && data.results.length > 0) {
        searchInput.value = '';
        renderInspirationCard({ title: '搜索结果', summary: '', usable_ideas: data.results.map(function(r) { return r.title + ': ' + r.snippet.slice(0, 100); }), sources: data.results });
        loadSearchHistory();
      } else {
        searchResult.innerHTML = '<div class="search-error">' + (data.error || '未找到结果') + '</div>';
      }
    } catch (e) {
      searchResult.innerHTML = '<div class="search-error">' + e.message + '</div>';
    } finally {
      btnSearchGo.disabled = false;
    }
  }

  function renderInspirationCard(insp) {
    var html = '<div class="inspiration-card">';
    html += '<h4>' + (insp.title || '搜索灵感') + '</h4>';
    if (insp.summary) html += '<div class="insp-summary">' + insp.summary + '</div>';
    if (insp.usable_ideas && insp.usable_ideas.length > 0) {
      html += '<ul class="insp-ideas">';
      insp.usable_ideas.forEach(function(idea, i) {
        html += '<li><span>' + idea + '</span><button class="btn-adopt-idea" data-idea="' + i + '">采用</button></li>';
      });
      html += '</ul>';
    }
    if (insp.cautions && insp.cautions.length > 0) {
      html += '<div class="insp-cautions">注意: ' + insp.cautions.join('; ') + '</div>';
    }
    if (insp.sources && insp.sources.length > 0) {
      html += '<div class="insp-sources">参考来源: ';
      insp.sources.forEach(function(s) {
        html += '<a href="' + s.url + '" target="_blank">' + (s.title || s.url).slice(0, 30) + '</a> ';
      });
      html += '</div>';
    }
    html += '</div>';
    searchResult.innerHTML = html;

    // Wire up adopt buttons
    $$('.btn-adopt-idea').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var idea = insp.usable_ideas[parseInt(this.dataset.idea)];
        searchPanel.classList.add('hidden');
        // Auto-send the adopted idea to the AI
        chatInput.value = '请参考这个方向来完善角色：' + idea;
        sendMessage();
      });
    });
  }

  async function loadSearchHistory() {
    if (!state.sessionId) return;
    try {
      var data = await apiCall('GET', '/api/sessions/' + state.sessionId + '/search-runs');
      var runs = data.runs || [];
      if (runs.length === 0) { searchHistory.innerHTML = ''; return; }
      var html = '<div class="history-title">搜索历史</div>';
      runs.slice(0, 8).forEach(function(run) {
        try {
          var q = JSON.parse(run.query_json);
          var inp = JSON.parse(run.inspiration_json);
          html += '<div class="history-item" data-query="' + (q.query || '') + '">';
          html += '<span class="history-query">' + (q.query || '').slice(0, 30) + '</span>';
          html += '<span class="history-title-text">' + (inp.title || '').slice(0, 20) + '</span>';
          html += '<span class="history-time">' + new Date(run.created_at).toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'}) + '</span>';
          html += '</div>';
        } catch(e) {}
      });
      searchHistory.innerHTML = html;
      // Click to re-search
      $$('.history-item').forEach(function(item) {
        item.addEventListener('click', function() {
          searchInput.value = this.dataset.query;
          doSearch();
        });
      });
    } catch(e) { searchHistory.innerHTML = ''; }
  }

  btnSearchGo.addEventListener('click', doSearch);
  searchInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') { e.preventDefault(); doSearch(); }
  });

  // ─── Auth ────────────────────────────────────────────
  function showAuth() { authOverlay.classList.remove('hidden'); hideError(authError); }
  function hideAuth() { authOverlay.classList.add('hidden'); }

  // Tab switching
  $$('.auth-tab').forEach(function(tab) {
    tab.addEventListener('click', function() {
      $$('.auth-tab').forEach(function(t) { t.classList.remove('active'); });
      this.classList.add('active');
      $$('.auth-form').forEach(function(f) { f.classList.add('hidden'); });
      var formId = 'auth-form-' + this.dataset.tab;
      var form = document.getElementById(formId);
      if (form) form.classList.remove('hidden');
    });
  });

  btnLogin.addEventListener('click', showAuth);
  btnCloseAuth.addEventListener('click', hideAuth);

  // Login
  $('#btn-login-submit').addEventListener('click', async function() {
    var u = $('#login-username').value.trim();
    var p = $('#login-password').value;
    if (!u || !p) { showError(authError, '请填写用户名和密码'); return; }
    try {
      var data = await apiCall('POST', '/api/auth/login', { username: u, password: p });
      showToast('登录成功', 'success');
      authChecked = true;
      btnCloseAuth.classList.remove('hidden');
      hideAuth();
      updateUserDisplay(data.user);
      showDashboard();
    } catch (e) { showError(authError, e.message); }
  });

  // Register
  $('#btn-register-submit').addEventListener('click', async function() {
    var u = $('#reg-username').value.trim();
    var p = $('#reg-password').value;
    if (u.length < 3) { showError(authError, '用户名至少3个字符'); return; }
    if (p.length < 8) { showError(authError, '密码至少8个字符'); return; }
    try {
      var nickname = $('#reg-nickname').value.trim() || null;
      var data = await apiCall('POST', '/api/auth/register', { username: u, password: p, nickname: nickname });
      showToast('注册成功', 'success');
      authChecked = true;
      btnCloseAuth.classList.remove('hidden');
      hideAuth();
      updateUserDisplay(data.user);
      showDashboard();
    } catch (e) { showError(authError, e.message); }
  });

  // Guest
  $('#btn-guest-submit').addEventListener('click', async function() {
    try {
      var data = await apiCall('POST', '/api/auth/guest');
      showToast('已进入游客模式', 'success');
      authChecked = true;
      btnCloseAuth.classList.remove('hidden');
      hideAuth();
      updateUserDisplay(data.user);
      showDashboard();
    } catch (e) { showError(authError, e.message); }
  });

  function updateUserDisplay(user) {
    if (!user) {
      userStatus.textContent = '';
      btnLogin.classList.remove('hidden');
      btnLogin.textContent = '登录';
      return;
    }
    var label = user.username;
    if (user.role === 'admin') label += ' [管理]';
    if (user.is_guest) label += ' (游客)';
    userStatus.innerHTML = '<span class="user-role">' + label + '</span>';
    btnLogin.textContent = '退出';
    btnLogin.onclick = async function() {
      try {
        await apiCall('POST', '/api/auth/logout');
        authChecked = false;
        updateUserDisplay(null);
        resetToWelcome();
        authOverlay.classList.remove('hidden');
        btnCloseAuth.classList.add('hidden');
        showToast('已退出登录', 'success');
      } catch (e) { showToast(e.message, 'error'); }
    };
  }

  // Check auth on load
  var authChecked = false;
  (async function checkAuth() {
    try {
      var data = await apiCall('GET', '/api/auth/me');
      updateUserDisplay(data.user);
      authChecked = true;
      authOverlay.classList.add('hidden');
      showDashboard();
    } catch (e) {
      updateUserDisplay(null);
      // Show login gate
      authOverlay.classList.remove('hidden');
      btnCloseAuth.classList.add('hidden');
      authChecked = false;
    }
  })();

  // Prevent closing auth modal when not logged in
  btnCloseAuth.addEventListener('click', function() {
    if (authChecked) hideAuth();
  });

  // Password visibility toggle
  $$('.pw-toggle').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var input = document.getElementById(this.dataset.target);
      if (input) {
        input.type = input.type === 'password' ? 'text' : 'password';
        this.textContent = input.type === 'password' ? '👁' : '🙈';
      }
    });
  });
  authOverlay.addEventListener('click', function(e) {
    if (e.target === authOverlay && authChecked) hideAuth();
  });

})();
