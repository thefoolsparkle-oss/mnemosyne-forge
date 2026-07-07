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

  function wireExclusiveAudio(root) {
    (root || document).querySelectorAll('audio').forEach(function(audio) {
      if (audio.dataset.exclusiveWired === '1') return;
      audio.dataset.exclusiveWired = '1';
      audio.addEventListener('play', function() {
        document.querySelectorAll('audio').forEach(function(other) {
          if (other !== audio && !other.paused) other.pause();
        });
      });
    });
  }

  document.addEventListener('play', function(e) {
    if (!e.target || e.target.tagName !== 'AUDIO') return;
    document.querySelectorAll('audio').forEach(function(other) {
      if (other !== e.target && !other.paused) other.pause();
    });
  }, true);

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
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
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
    if (data.ok === false) throw new Error(data.error || data.detail || '请求失败');
    return data;
  }

  function renderMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/(?:^|\n)(\d+)\. (.+?)(?=\n|$)/g, function (m, num, content) {
      return '\n<li>' + num + '. ' + content + '</li>';
    });
    html = html.replace(/((?:<li>.*?<\/li>\n?)+)/g, function (m) {
      return '<ol>' + m + '</ol>';
    });
    html = html.replace(/\n\n/g, '<br><br>');
    html = html.replace(/\n/g, '<br>');
    return html;
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function escapeAttr(value) {
    return escapeHtml(value);
  }

  // Generic DOM builder helper. Reduces raw innerHTML surface and centralizes
  // attribute escaping. `attrs` may include `className`, `textContent`, `innerHTML`,
  // event handlers (`on_*`) and arbitrary HTML attributes.
  function createEl(tag, attrs) {
    attrs = attrs || {};
    var el = document.createElement(tag);
    for (var key in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, key)) continue;
      var val = attrs[key];
      if (key === 'className') {
        el.className = val;
      } else if (key === 'textContent') {
        el.textContent = val;
      } else if (key === 'innerHTML') {
        el.innerHTML = val;
      } else if (key.indexOf('on_') === 0 && typeof val === 'function') {
        el.addEventListener(key.slice(3), val);
      } else if (key === 'dataset') {
        for (var dkey in val) {
          if (Object.prototype.hasOwnProperty.call(val, dkey)) {
            el.dataset[dkey] = val[dkey];
          }
        }
      } else if (key === 'children' && Array.isArray(val)) {
        val.forEach(function(child) {
          if (child) el.appendChild(child);
        });
      } else if (val != null) {
        el.setAttribute(key, String(val));
      }
    }
    return el;
  }

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
    scenario: '场景',
    abilities: '能力',
    weaknesses: '弱点',
    relationships: '关系',
    first_message: '开场白',
    example_dialogue: '示例对话',
  };

  function updateDraftPanel(draft) {
    state.draft = draft;
    loadDraftAssets();
    $$('.draft-field').forEach(function (el) {
      const field = el.dataset.field;
      const valueEl = el.querySelector('.field-value');
      if (!field || !valueEl) return;
      const val = draft[field];
      const isListField = ['personality','abilities','weaknesses','relationships','themes','tags'].includes(field);
      if (isListField) {
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
      if (draft.locked_fields && draft.locked_fields.includes(field)) el.classList.add('locked');
      else el.classList.remove('locked');
      if (!el._editBound) {
        el._editBound = true;
        el.addEventListener('click', function() {
          if (el.querySelector('input, textarea')) return;
          var valEl = el.querySelector('.field-value');
          var currentVal = draft[field];
          var isList = ['personality','abilities','weaknesses','relationships','themes','tags'].includes(field);
          var input = document.createElement(isList ? 'input' : 'textarea');
          input.className = 'field-edit';
          if (isList) {
            input.value = Array.isArray(currentVal) ? currentVal.join('、') : '';
            input.placeholder = '用顿号或逗号分隔';
          } else {
            input.value = (typeof currentVal === 'string') ? currentVal : '';
            input.placeholder = '输入内容...';
            input.rows = 3;
          }
          valEl.replaceWith(input);
          input.focus();
          async function saveEdit() {
            var newVal = input.value.trim();
            var update = {};
            if (isList) update[field] = newVal ? newVal.split(/[、,，]/).map(function(s) { return s.trim(); }).filter(Boolean) : [];
            else update[field] = newVal || null;
            try {
              var data = await apiCall('PATCH', '/api/sessions/' + state.sessionId + '/draft', { updates: update });
              if (data.draft) updateDraftPanel(data.draft);
              showToast('已保存', 'success');
            } catch (e) {
              showToast('保存失败: ' + e.message, 'error');
              updateDraftPanel(state.draft);
            }
          }
          input.addEventListener('blur', saveEdit);
          input.addEventListener('keydown', function(ev) {
            if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); input.blur(); }
            if (ev.key === 'Escape') updateDraftPanel(state.draft);
          });
        });
      }
    });
    const score = draft.completion_score || 0;
    const pct = Math.round(score * 100);
    var coreFields = ['name','core_concept','personality','appearance','background'];
    var filled = coreFields.filter(function(f) { return draft[f] && (typeof draft[f] !== 'object' || draft[f].length > 0); }).length;
    $('#completion-detail').textContent = '核心字段 ' + filled + '/' + coreFields.length;
    $('#completion-percent').textContent = pct + '%';
    $('#progress-fill').style.width = pct + '%';
    var draftTitle = draft.name || draft.core_concept;
    $('.draft-title').textContent = draftTitle ? '角色 · ' + draftTitle.slice(0, 15) : '角色草稿';
    const stage = draft.current_stage || 'core_concept';
    $('#current-stage').textContent = STAGE_LABELS[stage] || stage;
  }

  async function createSession(idea, fastMode) {
    hideError(welcomeError);
    setLoading(true, fastMode ? $('#btn-fast') : btnStart, fastMode ? '生成中…' : '创建中…');
    try {
      const data = await apiCall('POST', '/api/sessions', { initial_idea: idea, fast_mode: fastMode });
      state.sessionId = data.session_id;
      dashboard.classList.add('hidden');
      welcomeScreen.classList.add('hidden');
      workspace.classList.remove('hidden');
      btnBackDash.classList.remove('hidden');
      chatMessages.innerHTML = '';
      addMessage('user', idea);
      addMessage('assistant', data.assistant_message);
      if (data.draft) updateDraftPanel(data.draft);
      if (data.card) showCardPreview(data.card);
    } catch (e) {
      showError(welcomeError, e.message);
    } finally {
      var restoreBtn = fastMode ? $('#btn-fast') : btnStart;
      var restoreText = fastMode ? '一键生成角色卡' : '开始创作 · 逐步引导';
      setLoading(false, restoreBtn, restoreText);
    }
  }

  async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message || state.isLoading || !state.sessionId) return;
    chatInput.value = '';
    hideError(exportStatus);
    setLoading(true, btnSend, '发送中…');
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
    setLoading(true, btnExport, '导出中…');
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

  function showCardPreview(card) {
    var data = card.data || card;
    cardName.textContent = data.name || '未命名';
    cardTags.innerHTML = (data.tags || []).map(function(t) { return '<span class="card-tag">' + escapeHtml(t) + '</span>'; }).join('');
    cardDescription.textContent = data.description || '';
    cardPersonality.textContent = data.personality || '';
    cardScenario.textContent = data.scenario || '';
    cardFirstMes.textContent = data.first_mes || '';
    cardMesExample.textContent = data.mes_example || '';
    var greetings = $('#card-greetings');
    var greetsSection = $('#card-greetings-section');
    if (data.alternate_greetings && data.alternate_greetings.length > 0) {
      greetings.innerHTML = data.alternate_greetings.map(function(g) { return '<p class="card-quote">' + escapeHtml(g) + '</p>'; }).join('');
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

    // Show selected assets if available
    var extensions = data.extensions || {};
    var selectedAssets = extensions.mnemosyne_forge && extensions.mnemosyne_forge.selected_assets;
    if (selectedAssets) {
      var assetSection = document.getElementById('card-assets-section');
      if (!assetSection) {
        assetSection = createEl('div', { id: 'card-assets-section', className: 'card-section' });
        assetSection.appendChild(createEl('h4', { textContent: '绑定资产' }));
        assetSection.appendChild(createEl('div', { id: 'card-assets' }));
        var cardBody = document.querySelector('.card-body');
        if (cardBody) cardBody.appendChild(assetSection);
      }
      var assetsEl = document.getElementById('card-assets');
      assetsEl.innerHTML = '';

      if (selectedAssets.image) {
        var img = selectedAssets.image;
        var imgName = (img.path || '').split(/[/\\]/).pop();
        var imgMeta = img.metadata_json ? (typeof img.metadata_json === 'string' ? JSON.parse(img.metadata_json) : img.metadata_json) : (img.metadata || {});
        var imgItem = createEl('div', { className: 'card-asset-item' });
        imgItem.appendChild(createEl('strong', { textContent: '立绘' }));
        imgItem.appendChild(createEl('br'));
        if (imgName) {
          imgItem.appendChild(createEl('img', {
            src: '/exports/images/' + imgName,
            style: 'max-width:120px;border-radius:6px;margin:4px 0'
          }));
        }
        if (imgMeta.prompt) {
          imgItem.appendChild(createEl('span', {
            style: 'font-size:11px;color:var(--text-muted)',
            textContent: (imgMeta.prompt || '').slice(0, 80)
          }));
        }
        assetsEl.appendChild(imgItem);
      }
      if (selectedAssets.voice_identity) {
        var v = selectedAssets.voice_identity;
        var vMeta = v.metadata_json ? (typeof v.metadata_json === 'string' ? JSON.parse(v.metadata_json) : v.metadata_json) : (v.metadata || {});
        var voiceName = vMeta.voice_name || (v.path || '').slice(0, 16);
        var voiceId = (v.path || '').split(/[/\\]/).pop() || voiceName;
        var vItem = createEl('div', { className: 'card-asset-item' });
        vItem.appendChild(createEl('strong', { textContent: '声音' }));
        vItem.appendChild(createEl('br'));
        vItem.appendChild(createEl('span', {
          style: 'font-size:11px',
          textContent: voiceName + ' (' + voiceId.slice(0, 12) + '...)'
        }));
        assetsEl.appendChild(vItem);
      }
      if (selectedAssets.voice_audio) {
        var aName = (selectedAssets.voice_audio.path || '').split(/[/\\]/).pop();
        assetsEl.appendChild(createEl('audio', {
          controls: true,
          src: '/exports/voices/' + aName,
          style: 'width:100%;margin-top:4px'
        }));
      }
      if (!assetsEl.hasChildNodes()) {
        assetsEl.appendChild(createEl('p', { style: 'color:var(--text-muted)', textContent: '暂无绑定资产' }));
      }
      wireExclusiveAudio(assetsEl);
      assetSection.classList.remove('hidden');
    }
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
        var name = s.title || '未命名';
        var concept = s.core_concept || '';
        var score = Math.round((s.completion_score || 0) * 100);
        var date = new Date(s.updated_at).toLocaleDateString('zh-CN');

        var div = createEl('div', { className: 'library-item', dataset: { sessionId: s.id } });
        div.appendChild(createEl('div', { className: 'library-item-avatar', textContent: name[0] || '?' }));
        var info = createEl('div', { className: 'library-item-info' });
        info.appendChild(createEl('div', { className: 'library-item-name', textContent: name }));
        info.appendChild(createEl('div', { className: 'library-item-concept', textContent: concept || '无描述' }));
        div.appendChild(info);
        var meta = createEl('div', { className: 'library-item-meta' });
        meta.appendChild(createEl('div', { className: 'library-item-score', textContent: score + '%' }));
        meta.appendChild(createEl('div', { className: 'library-item-date', textContent: date }));
        div.appendChild(meta);
        div.appendChild(createEl('button', {
          type: 'button',
          className: 'library-item-del',
          innerHTML: '&times;',
          on_click: function(e) {
            e.stopPropagation();
            deleteSession(s.id, name);
          }
        }));
        div.addEventListener('click', function() { resumeSession(s.id); });
        libraryList.appendChild(div);
      });
      btnLibrary.textContent = '角色库 (' + sessions.length + ')';
    } catch (e) {
      libraryList.innerHTML = '<div class="library-empty">加载失败: ' + escapeHtml(e.message) + '</div>';
      btnLibrary.textContent = '角色库';
    }
  }

  async function resumeSession(sessionId) {
    try {
      setLoading(true, btnStart, '加载中…');
      var data = await apiCall('GET', '/api/sessions/' + sessionId + '/resume');
      state.sessionId = data.session_id;
      libraryOverlay.classList.add('hidden');
      dashboard.classList.add('hidden');
      welcomeScreen.classList.add('hidden');
      workspace.classList.remove('hidden');
      btnBackDash.classList.remove('hidden');
      chatMessages.innerHTML = '';
      (data.messages || []).forEach(function(m) {
        addMessage(m.role, m.content, new Date(m.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }));
      });
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
      if (state.sessionId === sessionId) showDashboard();
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  async function showDashboard() {
    welcomeScreen.classList.add('hidden');
    workspace.classList.add('hidden');
    cardOverlay.classList.add('hidden');
    dashboard.classList.remove('hidden');
    btnBackDash.classList.add('hidden');
  }

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

  function setLoading(loading, btn, originalText) {
    state.isLoading = loading;
    btn.disabled = loading;
    if (loading) {
      btn.dataset.originalText = originalText || btn.textContent;
      btn.textContent = btn.dataset.originalText || '处理中…';
    } else {
      btn.textContent = originalText || btn.dataset.originalText || btn.textContent;
      btn.disabled = false;
    }
  }

  btnStart.addEventListener('click', function () {
    const idea = initialIdea.value.trim();
    if (!idea) { showError(welcomeError, '请输入角色灵感'); return; }
    createSession(idea, false);
  });

  $('#btn-fast').addEventListener('click', function () {
    const idea = initialIdea.value.trim();
    if (!idea) { showError(welcomeError, '请输入角色灵感'); return; }
    createSession(idea, true);
  });

  initialIdea.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      btnStart.click();
    }
  });

  btnSend.addEventListener('click', sendMessage);

  chatInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  btnNewSession.addEventListener('click', function () {
    if (state.sessionId && state.draft && state.draft.completion_score > 0.1) {
      if (!confirm('确定要开始新角色吗？当前创作进度将丢失。')) return;
    }
    resetToWelcome();
    showDashboard();
  });

  btnExport.addEventListener('click', exportCard);

  var assetOverlay = null;
  var assetContent = null;

  function assetDisplayUrl(asset) {
    var meta = asset.metadata || {};
    if (meta.audio_url) return meta.audio_url;
    var p = asset.path || '';
    if (!p) return '';
    var name = p.split(/[\\/]/).pop();
    if (!name) return '';
    if ((asset.asset_type || '').indexOf('image_') === 0) return '/exports/images/' + name;
    if ((asset.asset_type || '').indexOf('voice_') === 0) return '/exports/voices/' + name;
    return '';
  }

  function assetTypeLabel(type) {
    var labels = {
      image_candidate: '立绘候选',
      image_locked: '已锁定立绘',
      voice_preview: '声音候选',
      voice_identity: '已锁定声音',
      voice_sample: '试听样本',
      voice_performance_candidate: '表演候选',
    };
    return labels[type] || type || '未分类';
  }

  function ensureAssetOverlay() {
    if (assetOverlay) return;
    assetOverlay = document.createElement('div');
    assetOverlay.className = 'asset-overlay hidden';
    assetOverlay.innerHTML =
      '<div class="asset-panel">' +
        '<div class="asset-panel-header">' +
          '<h3>资产历史</h3>' +
          '<div class="asset-panel-actions">' +
            '<select id="asset-type-filter" class="voice-select" style="margin-right:6px">' +
              '<option value="">全部类型</option>' +
              '<option value="image_locked">已锁定立绘</option>' +
              '<option value="image_candidate">立绘候选</option>' +
              '<option value="voice_identity">已锁定声音</option>' +
              '<option value="voice_preview">声音候选</option>' +
              '<option value="voice_sample">试听样本</option>' +
              '<option value="voice_performance_candidate">表演候选</option>' +
            '</select>' +
            '<button type="button" class="btn-adopt-idea" id="btn-asset-cleanup">清理未选</button>' +
            '<button type="button" class="btn-close-card" id="btn-asset-close">&times;</button>' +
          '</div>' +
        '</div>' +
        '<div id="asset-content" class="asset-content"></div>' +
      '</div>';
    document.body.appendChild(assetOverlay);
    assetContent = assetOverlay.querySelector('#asset-content');
    assetOverlay.querySelector('#btn-asset-close').addEventListener('click', function() {
      assetOverlay.classList.add('hidden');
    });
    assetOverlay.querySelector('#btn-asset-cleanup').addEventListener('click', async function() {
      if (!state.sessionId || !confirm('清理未选候选资产？已锁定的图像和声音会保留。')) return;
      try {
        var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/assets/cleanup', { keep_selected: true });
        showToast('已清理 ' + (data.removed_records || 0) + ' 条资产记录', 'success');
        await loadAssets();
      } catch(e) { showToast(e.message, 'error'); }
    });
    assetOverlay.querySelector('#asset-type-filter').addEventListener('change', function() {
      loadAssets(this.value || null);
    });
    assetOverlay.addEventListener('click', function(e) {
      if (e.target === assetOverlay) assetOverlay.classList.add('hidden');
    });
  }

  function renderAssets(assets) {
    assetContent.innerHTML = '';
    if (!assets.length) {
      assetContent.appendChild(createEl('div', { className: 'asset-empty', textContent: '还没有生成资产。' }));
      return;
    }
    var grouped = {};
    assets.forEach(function(asset) {
      var key = asset.asset_type || 'unknown';
      if (!grouped[key]) grouped[key] = [];
      grouped[key].push(asset);
    });
    var order = ['image_locked', 'image_candidate', 'voice_identity', 'voice_preview', 'voice_sample', 'voice_performance_candidate'];
    var keys = order.filter(function(k) { return grouped[k]; }).concat(Object.keys(grouped).filter(function(k) { return order.indexOf(k) < 0; }));

    keys.forEach(function(type) {
      var section = createEl('section', { className: 'asset-section' });
      section.appendChild(createEl('h4', { textContent: assetTypeLabel(type) }));
      var grid = createEl('div', { className: 'asset-grid' });

      grouped[type].forEach(function(asset) {
        var meta = asset.metadata || {};
        var url = assetDisplayUrl(asset);
        var cardClass = 'asset-card' + (asset.selected ? ' selected' : '');
        var card = createEl('article', { className: cardClass });

        if (url && type.indexOf('image_') === 0) {
          card.appendChild(createEl('img', { className: 'asset-thumb', src: url, alt: '' }));
        }
        if (url && type.indexOf('voice_') === 0) {
          card.appendChild(createEl('audio', { controls: true, src: url }));
        }

        var metaEl = createEl('div', { className: 'asset-meta' });
        metaEl.appendChild(createEl('strong', { textContent: meta.label || assetTypeLabel(type) }));
        metaEl.appendChild(createEl('span', { textContent: asset.provider || '' }));
        if (asset.created_at) {
          metaEl.appendChild(createEl('span', { textContent: new Date(asset.created_at).toLocaleString('zh-CN') }));
        }
        if (asset.selected) {
          metaEl.appendChild(createEl('em', { textContent: '已选中' }));
        }
        card.appendChild(metaEl);

        var actions = createEl('div', { className: 'asset-actions' });
        if (type === 'image_locked') {
          actions.appendChild(createEl('button', {
            type: 'button',
            className: 'btn-adopt-idea asset-variation-image',
            textContent: '生成变体',
            dataset: { id: String(asset.id) },
            on_click: async function() {
              try {
                ensureImageOverlay();
                imageOverlay.classList.remove('hidden');
                if (imageProviders.length === 0) await loadImageProviders();
                imageContent.innerHTML = '';
                imageContent.appendChild(createEl('div', { className: 'image-loading', textContent: '正在基于已锁定立绘生成一致性变体…' }));
                var body = getImageProviderBody();
                var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/image-variations', body);
                renderImageCandidates(data.candidates || []);
                await loadAssets();
              } catch(e) { showToast(e.message, 'error'); }
            }
          }));
        } else if (type === 'image_candidate') {
          actions.appendChild(createEl('button', {
            type: 'button',
            className: 'btn-adopt-idea asset-lock-image',
            textContent: '锁定为 canon',
            dataset: { id: String(asset.id), style: meta.style || '', prompt: meta.prompt || '' },
            on_click: async function() {
              try {
                var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/visual-canon-lock', {
                  asset_id: Number(this.dataset.id),
                  style: this.dataset.style || '',
                  prompt: this.dataset.prompt || '',
                });
                showToast(data.ok ? '已锁定视觉 canon' : '锁定失败', data.ok ? 'success' : 'error');
                await loadAssets();
              } catch(e) { showToast(e.message, 'error'); }
            }
          }));
        } else {
          actions.appendChild(createEl('button', {
            type: 'button',
            className: 'btn-adopt-idea asset-select',
            textContent: '选中',
            dataset: { id: String(asset.id), type: type },
            on_click: async function() {
              try {
                await apiCall('POST', '/api/sessions/' + state.sessionId + '/assets/' + this.dataset.id + '/select', { asset_type: this.dataset.type || '' });
                showToast('已选中资产', 'success');
                await loadAssets();
              } catch(e) { showToast(e.message, 'error'); }
            }
          }));
        }
        card.appendChild(actions);
        grid.appendChild(card);
      });

      section.appendChild(grid);
      assetContent.appendChild(section);
    });
    wireExclusiveAudio(assetContent);
  }

  async function loadAssets(assetType) {
    if (!state.sessionId) return;
    ensureAssetOverlay();
    assetContent.innerHTML = '';
    assetContent.appendChild(createEl('div', { className: 'asset-loading', textContent: '正在读取资产…' }));
    var url = '/api/sessions/' + state.sessionId + '/assets';
    if (assetType) url += '?asset_type=' + encodeURIComponent(assetType);
    var data = await apiCall('GET', url);
    renderAssets(data.assets || []);
  }

  function ensureAssetButton() {
    var actions = document.querySelector('.draft-actions');
    if (!actions || document.getElementById('btn-assets')) return;
    var btn = document.createElement('button');
    btn.id = 'btn-assets';
    btn.className = 'btn-draft-action';
    btn.type = 'button';
    btn.textContent = '资产历史';
    btn.addEventListener('click', async function() {
      if (!state.sessionId) return;
      ensureAssetOverlay();
      assetOverlay.classList.remove('hidden');
      try { await loadAssets(); } catch(e) { assetContent.innerHTML = '<div class="asset-error">' + escapeHtml(e.message) + '</div>'; }
    });
    actions.appendChild(btn);
  }

  ensureAssetButton();

  $('#btn-world').addEventListener('click', async function() {
    if (!state.sessionId) return;
    try {
      showToast('正在生成世界观…', 'success');
      var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/world');
      if (data.ok) showToast('世界观已生成', 'success');
    } catch(e) { showToast(e.message, 'error'); }
  });

  var imageOverlay = null;
  var imageContent = null;

  var imageProviders = [];

  async function loadImageProviders() {
    try {
      var data = await apiCall('GET', '/api/image-providers');
      imageProviders = data.providers || [];
    } catch (e) {
      imageProviders = [
        { name: 'pollinations', label: 'Pollinations（免费默认）', requires_api_key: false },
        { name: 'stability', label: 'Stability AI', requires_api_key: true },
        { name: 'openai', label: 'OpenAI DALL-E', requires_api_key: true },
        { name: 'seedream', label: 'Seedream (火山方舟)', requires_api_key: true },
        { name: 'custom', label: '其他（自定义）', requires_api_key: true },
      ];
    }
  }

  function renderImageProviderSelect(container) {
    var existing = container.querySelector('.image-provider-select');
    if (existing) return existing;
    var wrap = createEl('div', { className: 'image-provider-select', style: 'margin-right:8px' });
    var select = createEl('select', { id: 'image-provider-select', className: 'voice-select' });
    imageProviders.forEach(function(p) {
      select.appendChild(createEl('option', { value: p.name, textContent: p.label }));
    });
    wrap.appendChild(select);

    var customWrap = createEl('div', { className: 'image-provider-custom hidden', style: 'margin-top:6px' });
    customWrap.appendChild(createEl('input', { type: 'text', id: 'image-custom-base-url', className: 'voice-edit-input', placeholder: 'API base_url', style: 'width:100%;margin-bottom:4px' }));
    customWrap.appendChild(createEl('input', { type: 'text', id: 'image-custom-model', className: 'voice-edit-input', placeholder: '模型名', style: 'width:100%;margin-bottom:4px' }));
    customWrap.appendChild(createEl('input', { type: 'password', id: 'image-custom-api-key', className: 'voice-edit-input', placeholder: 'API Key', style: 'width:100%' }));
    wrap.appendChild(customWrap);

    select.addEventListener('change', function() {
      customWrap.classList.toggle('hidden', this.value !== 'custom');
    });
    container.appendChild(wrap);
    return select;
  }

  function getImageProviderBody() {
    var providerEl = document.getElementById('image-provider-select');
    var provider = providerEl ? providerEl.value : 'pollinations';
    var body = { provider: provider };
    if (provider === 'custom') {
      body.custom_base_url = (document.getElementById('image-custom-base-url') || {}).value || '';
      body.custom_model = (document.getElementById('image-custom-model') || {}).value || '';
      body.custom_api_key = (document.getElementById('image-custom-api-key') || {}).value || '';
    }
    return body;
  }

  function ensureImageOverlay() {
    if (imageOverlay) return;
    imageOverlay = document.createElement('div');
    imageOverlay.className = 'image-overlay hidden';
    imageOverlay.innerHTML =
      '<div class="image-panel">' +
        '<div class="image-panel-header">' +
          '<h3>立绘候选</h3>' +
          '<div class="image-panel-actions" id="image-panel-actions"></div>' +
          '<button type="button" class="btn-close-card" id="btn-image-close">&times;</button>' +
        '</div>' +
        '<div id="image-content" class="image-content"></div>' +
      '</div>';
    document.body.appendChild(imageOverlay);
    imageContent = imageOverlay.querySelector('#image-content');
    var actions = imageOverlay.querySelector('#image-panel-actions');
    renderImageProviderSelect(actions);
    imageOverlay.querySelector('#btn-image-close').addEventListener('click', function() {
      imageOverlay.classList.add('hidden');
    });
    imageOverlay.addEventListener('click', function(e) {
      if (e.target === imageOverlay) imageOverlay.classList.add('hidden');
    });
  }

  function renderImageCandidates(candidates) {
    imageContent.innerHTML = '';
    if (!candidates.length) {
      imageContent.appendChild(createEl('div', { className: 'image-empty', textContent: '没有生成可用候选。' }));
      return;
    }
    var grid = createEl('div', { className: 'image-candidate-grid' });

    candidates.forEach(function(c) {
      var card = createEl('div', { className: 'image-candidate' });
      card.appendChild(createEl('div', { className: 'image-candidate-title', textContent: c.label || ('候选 ' + c.index) }));

      if (c.image_url) {
        card.appendChild(createEl('img', { src: c.image_url, alt: c.label || 'image candidate' }));
        card.appendChild(createEl('div', {
          className: 'image-critique-note',
          textContent: '当前评审基于 prompt 文字，尚未对真实生成图做视觉判断。'
        }));
        if (c.critique && c.critique.overall_score != null) {
          var critiqueText = 'Prompt 评分: ' + Math.round(c.critique.overall_score) + '/10';
          if (c.critique.passed === false) critiqueText += ' 未通过';
          card.appendChild(createEl('div', { className: 'image-critique', textContent: critiqueText }));
        }
      } else {
        var errBox = createEl('div', { className: 'image-error' });
        errBox.appendChild(createEl('strong', { textContent: c.label || '生成失败' }));
        errBox.appendChild(createEl('br'));
        errBox.appendChild(document.createTextNode(c.error || '未知错误'));
        errBox.appendChild(createEl('br'));
        errBox.appendChild(createEl('button', {
          type: 'button',
          className: 'btn-adopt-idea image-retry-btn',
          textContent: '重试此风格',
          dataset: { style: c.style || '', prompt: c.prompt || '', negPrompt: c.negative_prompt || '' },
          on_click: async function() {
            var style = this.dataset.style;
            var prompt = this.dataset.prompt;
            var negPrompt = this.dataset.negPrompt || '';
            showToast('正在重试「' + style + '」风格……', 'success');
            try {
              var retryBody = getImageProviderBody();
              retryBody.retry_style = style;
              if (prompt) { retryBody.retry_prompt = prompt; retryBody.retry_negative_prompt = negPrompt; }
              var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/image-candidates', retryBody);
              renderImageCandidates(data.candidates || []);
            } catch(e) { showToast(e.message, 'error'); }
          }
        }));
        card.appendChild(errBox);
      }

      var actions = createEl('div', { className: 'image-candidate-actions' });
      if (c.asset_id) {
        actions.appendChild(createEl('button', {
          type: 'button',
          className: 'btn-adopt-idea image-lock-btn',
          textContent: '锁定',
          dataset: { asset: c.asset_id, style: c.style || '', prompt: c.prompt || '' },
          on_click: async function() {
            try {
              var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/visual-canon-lock', {
                asset_id: Number(this.dataset.asset),
                style: this.dataset.style || '',
                prompt: this.dataset.prompt || '',
              });
              showToast(data.ok ? '已锁定角色视觉 canon' : '锁定失败', data.ok ? 'success' : 'error');
            } catch(e) { showToast(e.message, 'error'); }
          }
        }));
      }
      if (c.prompt) {
        actions.appendChild(createEl('button', {
          type: 'button',
          className: 'btn-adopt-idea image-copy-btn',
          textContent: '复制 Prompt',
          dataset: { prompt: c.prompt },
          on_click: function() {
            navigator.clipboard.writeText(this.dataset.prompt || '').then(function() {
              showToast('Prompt 已复制', 'success');
            }).catch(function() {
              showToast('复制失败', 'error');
            });
          }
        }));
      }
      card.appendChild(actions);
      grid.appendChild(card);
    });

    imageContent.appendChild(grid);
  }

  $('#btn-image').addEventListener('click', async function() {
    if (!state.sessionId) return;
    ensureImageOverlay();
    imageOverlay.classList.remove('hidden');
    if (imageProviders.length === 0) await loadImageProviders();
    imageContent.innerHTML = '';
    imageContent.appendChild(createEl('div', { className: 'image-loading', textContent: '正在生成三张候选立绘…' }));
    try {
      var body = getImageProviderBody();
      var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/image-candidates', body);
      renderImageCandidates(data.candidates || []);
    } catch(e) {
      imageContent.innerHTML = '';
      imageContent.appendChild(createEl('div', { className: 'image-error', textContent: e.message }));
    }
  });

  $('#btn-bridge').addEventListener('click', async function() {
    if (!state.sessionId) return;
    try {
      showToast('正在导入忆界树…', 'success');
      var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/import-to-mnemosyne', {});
      if (data.ok) showToast(data.message || '已导入忆界树', 'success');
      else showToast(data.error || '导入失败', 'error');
    } catch(e) { showToast(e.message, 'error'); }
  });

  // Voice panel
  var voiceOverlay = $('#voice-overlay');
  var voiceContent = $('#voice-content');
  var voiceOptions = null;

  $('#btn-voice').addEventListener('click', function() {
    voiceOverlay.classList.remove('hidden');
    loadVoiceOptions();
  });
  $('#btn-voice-close').addEventListener('click', function() {
    voiceOverlay.classList.add('hidden');
  });
  voiceOverlay.addEventListener('click', function(e) {
    if (e.target === voiceOverlay) voiceOverlay.classList.add('hidden');
  });

  $('#btn-voice-analyze').addEventListener('click', async function() {
    if (!state.sessionId) return;
    voiceContent.innerHTML = '<div class="voice-loading">分析中…</div>';
    try {
      if (!voiceOptions) await loadVoiceOptions();
      var data = await apiCall('GET', '/api/sessions/' + state.sessionId + '/voice-profile');
      renderVoiceProfile(data.voice_profile);
    } catch(e) { voiceContent.innerHTML = '<div class="voice-loading" style="color:var(--error)">' + escapeHtml(e.message) + '</div>'; }
  });

  $('#btn-voice-generate').addEventListener('click', async function() {
    if (!state.sessionId) return;
    // P0: check provider select for ElevenLabs voice_id requirement
    var providerEl = document.getElementById('voice-provider-select');
    var provider = providerEl ? providerEl.value : ((voiceOptions && voiceOptions.default_provider) || 'elevenlabs');
    if (provider === 'elevenlabs') {
      try {
        var profileResp = await apiCall('GET', '/api/sessions/' + state.sessionId + '/voice-profile');
        var hints = (profileResp.voice_profile || {}).provider_hints || {};
        if (!hints.elevenlabs_voice_id) {
          showToast('请先生成专属音色并选定一个，再试听', 'error');
          return;
        }
      } catch(e) { /* proceed to TTS anyway */ }
    }
    try {
      var providerEl = document.getElementById('voice-provider-select');
      var provider = providerEl ? providerEl.value : ((voiceOptions && voiceOptions.default_provider) || 'elevenlabs');
      var body = { provider: provider };
      // Pass reference_id if set (for Fish Audio)
      var refEl = document.getElementById('voice-edit-ref');
      if (refEl && refEl.value.trim()) {
        body.provider_hints = { fish_reference_id: refEl.value.trim() };
      }
      var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/voice-sample', body);
      if (data.ok) {
        var player = voiceContent.querySelector('.voice-sample-player');
        if (player) {
          player.innerHTML = '<audio controls src="' + escapeAttr(data.audio_url || data.audio_path) + '"></audio>';
          wireExclusiveAudio(player);
        }
        // Render per-unit TTS results when available
        if (data.per_unit_results && data.per_unit_results.length > 0) {
          var sampleSection = voiceContent.querySelector('.voice-sample');
          renderPerUnitResults(data.per_unit_results, voiceContent, sampleSection);
        }
        showToast('试听已生成', 'success');
      } else {
        showToast(data.error || '生成失败', 'error');
      }
    } catch(e) { showToast(e.message, 'error'); }
  });

  $('#btn-voice-candidates').addEventListener('click', async function() {
    if (!state.sessionId) return;
    voiceContent.innerHTML = '<div class="voice-loading">生成三候选音色…</div>';
    try {
      var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/voice-sample-candidates', { provider: 'elevenlabs' });
      if (!data.ok) {
        voiceContent.innerHTML = '<div class="voice-loading" style="color:var(--error)">三候选生成失败：' + escapeHtml(data.error || '未知错误') + '</div><div class="voice-summary">请确认 ElevenLabs API Key 有效且有可用额度，然后重试。</div>';
        return;
      }
      renderVoiceCandidates(data.candidates || [], data.provider || 'elevenlabs');
    } catch(e) { voiceContent.innerHTML = '<div class="voice-loading" style="color:var(--error)">' + escapeHtml(e.message) + '</div>'; }
  });

  function renderVoiceCandidates(candidates, provider) {
    voiceContent.innerHTML = '';
    var isVoiceIdentity = provider === 'elevenlabs';
    var list = createEl('div', { className: 'voice-candidate-list' });
    list.appendChild(createEl('div', { className: 'voice-summary', textContent: isVoiceIdentity ? '三候选音色对比' : '表现参数对比' }));

    candidates.forEach(function(c) {
      var card = createEl('div', { className: 'voice-candidate' });
      var header = createEl('div', { className: 'voice-candidate-header' });
      header.appendChild(createEl('strong', { textContent: c.label || ('候选 ' + c.index) }));
      if (c.generated_voice_id) {
        header.appendChild(createEl('button', {
          type: 'button',
          className: 'btn-adopt-idea voice-select-candidate',
          textContent: '选择',
          dataset: { index: String(c.index || ''), generated: c.generated_voice_id },
          on_click: async function() {
            try {
              var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/voice-sample-candidates/select', { index: Number(this.dataset.index || 1), generated_voice_id: this.dataset.generated || '' });
              if (data.voice_profile) renderVoiceProfile(data.voice_profile);
              showToast('已保存这个角色音色', 'success');
            } catch(e) { showToast(e.message, 'error'); }
          }
        }));
      }
      card.appendChild(header);
      if (c.audio_url) {
        card.appendChild(createEl('audio', { controls: true, src: c.audio_url, style: 'width:100%;margin-top:4px' }));
      } else if (c.error) {
        card.appendChild(createEl('div', { className: 'voice-loading', style: 'color:var(--error)', textContent: c.error }));
      }
      list.appendChild(card);
    });

    voiceContent.appendChild(list);
    wireExclusiveAudio(voiceContent);
  }

  function renderPerUnitResults(perUnit, parentNode, afterNode) {
    if (!perUnit || !perUnit.length) return;
    var existing = parentNode.querySelector('.voice-per-unit');
    if (existing) existing.remove();
    var container = createEl('div', { className: 'voice-per-unit' });
    container.appendChild(createEl('div', { className: 'voice-summary', style: 'margin-top:8px', textContent: '逐句试听' }));

    perUnit.forEach(function(pu) {
      if (pu.error) {
        container.appendChild(createEl('div', { className: 'voice-loading', style: 'color:var(--error)', textContent: '第' + (pu.unit_index + 1) + '句失败: ' + pu.error }));
        return;
      }
      if (!pu.audio_path) return;

      var puAudioUrl = '/exports/voices/' + pu.audio_path.replace(/\\/g, '/').split('/').pop();
      var item = createEl('div', { className: 'voice-unit-item', dataset: { unitIndex: String(pu.unit_index) } });

      var textLine = createEl('div', { className: 'voice-unit-text' });
      textLine.appendChild(document.createTextNode('#' + (pu.unit_index + 1) + ' ' + (pu.clean_text || '')));
      var badges = [];
      if (pu.emotion) badges.push(pu.emotion);
      if (pu.speed) badges.push(pu.speed);
      if (pu.volume) badges.push(pu.volume);
      if (pu.context) badges.push(pu.context);
      if (badges.length > 0) {
        var badgeWrap = createEl('span', { className: 'voice-unit-badges' });
        badges.forEach(function(b) {
          badgeWrap.appendChild(createEl('span', { className: 'voice-unit-badge', textContent: b }));
        });
        textLine.appendChild(badgeWrap);
      }
      item.appendChild(textLine);
      item.appendChild(createEl('audio', { controls: true, src: puAudioUrl }));

      var unitMeta = createEl('div', { className: 'voice-unit-meta', style: 'font-size:11px;color:var(--text-muted)' });
      unitMeta.appendChild(document.createTextNode('emotion=' + (pu.emotion || '—') + ' speed=' + (pu.speed || '—') + ' volume=' + (pu.volume || '—')));
      item.appendChild(unitMeta);

      var unitActions = createEl('div', { className: 'voice-unit-actions', style: 'margin-top:4px' });
      unitActions.appendChild(createEl('button', {
        type: 'button',
        className: 'btn-search-go',
        style: 'padding:2px 8px;font-size:12px',
        textContent: '重生成此句',
        dataset: { unitIndex: String(pu.unit_index) },
        on_click: async function() {
          var btn = this;
          btn.disabled = true;
          btn.textContent = '生成中…';
          try {
            var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/voice-unit-regenerate', { unit_index: Number(btn.dataset.unitIndex) });
            if (data.ok) {
              var audio = item.querySelector('audio');
              if (audio) audio.src = data.audio_url;
              showToast('已重生成第' + (data.unit_index + 1) + '句', 'success');
            } else {
              showToast(data.error || '重生成失败', 'error');
            }
          } catch(e) { showToast(e.message, 'error'); }
          btn.disabled = false;
          btn.textContent = '重生成此句';
        }
      }));
      unitActions.appendChild(createEl('button', {
        type: 'button',
        className: 'btn-adopt-idea',
        style: 'margin-left:6px;padding:2px 8px;font-size:12px',
        textContent: '设为最佳',
        dataset: { unitIndex: String(pu.unit_index) },
        on_click: async function() {
          try {
            await apiCall('POST', '/api/sessions/' + state.sessionId + '/voice-unit-favorite', { unit_index: Number(this.dataset.unitIndex) });
            showToast('已保存为最佳句参数', 'success');
          } catch(e) { showToast(e.message, 'error'); }
        }
      }));
      item.appendChild(unitActions);
      container.appendChild(item);
    });

    renderListeningChecklist(container);

    if (afterNode && afterNode.parentNode) {
      afterNode.parentNode.insertBefore(container, afterNode.nextSibling);
    } else {
      parentNode.appendChild(container);
    }
    wireExclusiveAudio(container);
  }

  function renderListeningChecklist(container) {
    var existing = container.querySelector('.voice-listening-checklist');
    if (existing) return;
    var wrap = createEl('div', { className: 'voice-listening-checklist', style: 'margin-top:12px;padding:8px;border:1px solid var(--border);border-radius:6px' });
    wrap.appendChild(createEl('div', { className: 'voice-summary', textContent: '听感自检清单' }));
    var items = [
      '是否像真人（非播音腔/非机器感）',
      '是否像这个角色',
      '中文断句是否自然',
      '情绪与台词是否匹配',
      '语速是否合适',
    ];
    items.forEach(function(label) {
      var row = createEl('label', { style: 'display:block;font-size:12px;margin:4px 0' });
      row.appendChild(createEl('input', { type: 'checkbox' }));
      row.appendChild(document.createTextNode(' ' + label));
      wrap.appendChild(row);
    });
    container.appendChild(wrap);
  }

  $('#btn-voice-advanced-toggle').addEventListener('click', function() {
    var adv = $('#voice-advanced');
    var hidden = adv.classList.toggle('hidden');
    this.textContent = hidden ? '▸ 高级：Fish Audio / 参考音频' : '▾ 高级：Fish Audio / 参考音频';
  });

  $('#btn-voice-cast').addEventListener('click', async function() {
    if (!state.sessionId) return;
    voiceContent.innerHTML = '<div class="voice-loading">正在生成专属音色……</div>';
    try {
      var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/voice-sample-candidates', { provider: 'elevenlabs' });
      renderVoiceCandidates(data.candidates || [], data.provider || 'elevenlabs');
      if (data.ok === false) showToast(data.error || '生成失败', 'error');
    } catch(e) { voiceContent.innerHTML = '<div class="voice-loading" style="color:var(--error)">' + escapeHtml(e.message) + '</div>'; }
  });

  $('#btn-voice-ref-upload').addEventListener('click', async function() {
    if (!state.sessionId) return;
    var fileInput = document.getElementById('voice-ref-file');
    var transcriptInput = document.getElementById('voice-ref-transcript');
    if (!fileInput.files || !fileInput.files[0]) { showToast('请选择一段中文参考音频', 'error'); return; }
    var transcript = transcriptInput.value.trim();
    if (!transcript) { showToast('请填写参考音频逐字稿', 'error'); return; }
    var form = new FormData();
    form.append('file', fileInput.files[0]);
    form.append('transcript', transcript);
    form.append('label', '角色中文参考音频');
    try {
      var resp = await fetch('/api/sessions/' + state.sessionId + '/voice-reference', { method: 'POST', body: form });
      var data = await resp.json();
      if (!resp.ok || data.ok === false) throw new Error(data.error || data.detail || '上传失败');
      showToast('已绑定参考音频，Fish 会优先使用它生成角色声音', 'success');
      fileInput.value = '';
      transcriptInput.value = '';
    } catch(e) { showToast(e.message, 'error'); }
  });

  // Dialogue Rehearsal
  $('#btn-voice-rehearsal').addEventListener('click', function() {
    if (!state.sessionId) return;
    var rhOverlay = document.getElementById('rehearsal-overlay');
    var rhContent = document.getElementById('rehearsal-content');
    rhOverlay.classList.remove('hidden');
    rhContent.innerHTML = '';
    var sceneCtx = (state.draft && state.draft.scenario) ? state.draft.scenario : '';
    rhContent.appendChild(createEl('div', { className: 'voice-sample-text', style: 'margin-bottom:8px', textContent: '场景: ' + (sceneCtx || '未设定') }));
    rhContent.appendChild(createEl('textarea', { id: 'rh-user-line', className: 'voice-edit-input', rows: 2, placeholder: '输入一句你对角色说的话…', style: 'width:100%;margin-bottom:8px' }));
    rhContent.appendChild(createEl('button', { id: 'btn-rh-go', className: 'btn-search-go', textContent: '发送' }));
    rhContent.appendChild(createEl('div', { id: 'rh-result' }));
    document.getElementById('btn-rh-go').addEventListener('click', async function() {
      var userLine = document.getElementById('rh-user-line').value.trim();
      if (!userLine) { showToast('请输入一句话', 'error'); return; }
      var resultEl = document.getElementById('rh-result');
      resultEl.innerHTML = '<div class="voice-loading">角色正在思考…</div>';
      try {
        var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/dialogue-rehearsal', {
          user_line: userLine,
          scene_context: sceneCtx,
          generate_audio: true,
        });
        var beat = data.beat || {};
        resultEl.innerHTML = '';
        if (data.response_text) {
          resultEl.appendChild(createEl('div', { className: 'voice-summary', style: 'margin-top:10px', textContent: '角色回应' }));
          resultEl.appendChild(createEl('div', { className: 'voice-sample-text', style: 'font-size:15px;padding:8px 12px;margin:6px 0', textContent: data.response_text }));
          if (data.audio_url) {
            resultEl.appendChild(createEl('audio', { controls: true, src: data.audio_url, style: 'width:100%;margin-top:4px' }));
          }
        }
        resultEl.appendChild(createEl('div', { className: 'voice-summary', textContent: '拍点分析' }));
        var grid = createEl('div', { className: 'voice-grid' });
        var beatFields = [
          ['场景状态', beat.scene_state], ['用户意图', beat.user_intent],
          ['角色内心', beat.character_inner_reaction], ['关系变化', beat.relationship_delta],
          ['本轮目的', beat.beat_goal], ['回应方式', beat.response_mode],
        ];
        beatFields.forEach(function(f) {
          var item = createEl('div', { className: 'voice-item' });
          item.appendChild(createEl('div', { className: 'voice-item-label', textContent: f[0] }));
          item.appendChild(createEl('div', { className: 'voice-item-value', textContent: f[1] || '—' }));
          grid.appendChild(item);
        });
        var vd = beat.voice_direction || {};
        [['情绪', vd.emotion], ['音量', vd.volume], ['语速', vd.speed], ['停顿', vd.pause]].forEach(function(f) {
          var item = createEl('div', { className: 'voice-item' });
          item.appendChild(createEl('div', { className: 'voice-item-label', textContent: f[0] }));
          item.appendChild(createEl('div', { className: 'voice-item-value', textContent: f[1] || '—' }));
          grid.appendChild(item);
        });
        resultEl.appendChild(grid);
      } catch(e) { resultEl.innerHTML = '<div class="voice-loading" style="color:var(--error)">' + escapeHtml(e.message) + '</div>'; }
    });
  });
  $('#btn-rehearsal-close').addEventListener('click', function() {
    document.getElementById('rehearsal-overlay').classList.add('hidden');
  });
  document.getElementById('rehearsal-overlay').addEventListener('click', function(e) {
    if (e.target === this) this.classList.add('hidden');
  });

  async function loadVoiceOptions() {
    try {
      voiceOptions = await apiCall('GET', '/api/voice-options');
    } catch(e) {
      voiceOptions = {
        default_provider: 'elevenlabs',
        providers: ['elevenlabs', 'edge_tts', 'fish_audio'],
        fish_requires_reference_id: false,
        fish_prompt_without_reference: true,
        fish_voice_library: [],
      };
    }
  }

  function renderVoiceProfile(vp) {
    var fields = [
      ['声音年龄', vp.voice_age], ['性别倾向', vp.gender_tone], ['音色', vp.timbre],
      ['音高', vp.pitch], ['语速', vp.speed], ['音量', vp.volume],
      ['情绪表达', vp.emotion_level], ['停顿方式', vp.pause_style], ['咬字', vp.articulation],
      ['距离感', vp.distance_feeling], ['情绪色彩', (vp.emotional_color || []).join('、')],
    ];
    var grid = '<div class="voice-grid">';
    fields.forEach(function(f) { grid += '<div class="voice-item"><div class="voice-item-label">'+escapeHtml(f[0])+'</div><div class="voice-item-value">'+escapeHtml(f[1]||'—')+'</div></div>'; });
    grid += '</div>';
    var html = '';
    if (vp.voice_summary) html += '<div class="voice-summary">' + escapeHtml(vp.voice_summary) + '</div>';
    if (vp.reason) html += '<div class="voice-reason">' + escapeHtml(vp.reason) + '</div>';
    if (vp.reference_strategy) html += '<div class="voice-fish-note">' + escapeHtml(vp.reference_strategy) + '</div>';
    html += grid;
    if (vp.sample_lines && vp.sample_lines.length > 0) {
      html += '<div class="voice-sample-lines"><div class="voice-summary">角色台词 <button id="btn-regen-lines" class="btn-search-go" style="margin-left:8px;padding:2px 10px;font-size:12px">重新生成</button></div>';
      vp.sample_lines.forEach(function(line, idx) {
        var badges = [];
        if (line.emotion) badges.push('<span class="voice-unit-badge">' + escapeHtml(line.emotion) + '</span>');
        if (line.context) badges.push('<span class="voice-unit-badge">' + escapeHtml(line.context) + '</span>');
        html += '<div class="voice-line-item"><span class="voice-line-index">' + (idx+1) + '.</span> <span class="voice-line-text">' + escapeHtml(line.text || '') + '</span><span class="voice-line-badges">' + badges.join(' ') + '</span></div>';
      });
      html += '</div>';
    }
    if (vp.sample_text) html += '<div class="voice-sample"><div class="voice-sample-text">"' + escapeHtml(vp.sample_text) + '"</div><div class="voice-sample-player"></div></div>';
    if (vp.warnings && vp.warnings.length > 0) html += '<div class="voice-warnings">' + escapeHtml(vp.warnings.join('; ')) + '</div>';
    var hints = vp.provider_hints || {};
    var directive = hints.fish_tts_directive || vp.fish_tts_directive || {};
    var prosody = directive.prosody || {};
    var defaultProvider = (voiceOptions && voiceOptions.default_provider) || 'elevenlabs';
    var provider = defaultProvider;
    if (hints.elevenlabs_voice_id) provider = 'elevenlabs';
    else if (hints.provider && hints.provider !== 'fish_audio') provider = hints.provider;
    else if (hints.provider && defaultProvider !== 'elevenlabs') provider = hints.provider;
    var library = (voiceOptions && voiceOptions.fish_voice_library) || [];
    html += '<div class="voice-provider-section"><label>试听引擎</label><select id="voice-provider-select" class="voice-select">';
    var providerLabels = { elevenlabs: 'ElevenLabs（专属音色 / 中文 TTS）', edge_tts: 'Edge TTS（按性别/音高自动匹配）', fish_audio: 'Fish Audio（reference_id / 参考音频）' };
    ((voiceOptions && voiceOptions.providers) || ['elevenlabs', 'edge_tts', 'fish_audio']).forEach(function(name) { html += '<option value="' + escapeAttr(name) + '"' + (provider === name ? ' selected' : '') + '>' + escapeHtml(providerLabels[name] || name) + '</option>'; });
    html += '</select></div>';
    html += '<div class="voice-provider-section"><label>Fish 音色</label><select id="voice-fish-library" class="voice-select"><option value="">手动填写 reference_id</option>';
    library.forEach(function(item) { var disabled = item.configured ? '' : ' disabled'; var selected = item.reference_id && item.reference_id === hints.fish_reference_id ? ' selected' : ''; html += '<option value="' + escapeAttr(item.reference_id) + '"' + disabled + selected + '>' + escapeHtml(item.label + (item.configured ? '' : '（未配置）')) + '</option>'; });
    html += '</select></div>';
    html += '<div class="voice-provider-section"><label>Fish 表演标签</label><input type="text" id="voice-fish-prefix" class="voice-edit-input" placeholder="例如 (calm) (sad)" value="' + escapeAttr(directive.text_prefix || hints.fish_voice_prompt || vp.fish_voice_prompt || '') + '"></div>';
    html += '<div class="voice-provider-section"><label>Fish 语速 / 音量</label><div class="voice-prosody-row"><input type="number" id="voice-fish-speed" class="voice-number-input" min="0.7" max="1.2" step="0.01" value="' + (prosody.speed || 0.9) + '"><input type="number" id="voice-fish-volume" class="voice-number-input" min="-8" max="3" step="1" value="' + (prosody.volume || -3) + '"></div></div>';
    if (directive.performance_note) html += '<div class="voice-fish-note">' + escapeHtml(directive.performance_note) + '</div>';
    if (directive.avoid && directive.avoid.length) html += '<div class="voice-warnings">避免: ' + escapeHtml(directive.avoid.join('、')) + '</div>';
    html += '<div class="voice-edit-section"><input type="text" id="voice-edit-ref" class="voice-edit-input" placeholder="Fish reference_id，例如 8ef4..." value="' + escapeAttr(hints.fish_reference_id || '') + '"><button id="btn-voice-save" class="btn-search-go">保存设置</button></div>';
    voiceContent.innerHTML = html;
    // Wire regenerate lines button (after innerHTML set)
    var btnRegen = document.getElementById('btn-regen-lines');
    if (btnRegen) btnRegen.addEventListener('click', async function() {
      if (!state.sessionId) return;
      btnRegen.textContent = '生成中…'; btnRegen.disabled = true;
      try {
        var regenData = await apiCall('POST', '/api/sessions/' + state.sessionId + '/voice-profile/analyze');
        if (regenData.voice_profile) renderVoiceProfile(regenData.voice_profile);
        showToast('台词已重新生成', 'success');
      } catch(e) { showToast(e.message, 'error'); btnRegen.textContent = '重新生成'; btnRegen.disabled = false; }
    });
    var librarySelect = document.getElementById('voice-fish-library');
    if (librarySelect) librarySelect.addEventListener('change', function() { var refInput = document.getElementById('voice-edit-ref'); if (refInput) refInput.value = this.value; });
    var btnSave = document.getElementById('btn-voice-save');
    if (btnSave) btnSave.addEventListener('click', async function() {
      var providerSelect = document.getElementById('voice-provider-select');
      var refId = document.getElementById('voice-edit-ref').value.trim();
      var fishPrefix = document.getElementById('voice-fish-prefix').value.trim();
      var fishSpeed = Number(document.getElementById('voice-fish-speed').value || 0.9);
      var fishVolume = Number(document.getElementById('voice-fish-volume').value || -3);
      var updates = { provider_hints: { provider: providerSelect ? providerSelect.value : 'edge_tts' } };
      if (refId) updates.provider_hints.fish_reference_id = refId;
      updates.fish_tts_directive = { text_prefix: fishPrefix, prosody: { speed: fishSpeed, volume: fishVolume } };
      updates.provider_hints.fish_tts_directive = updates.fish_tts_directive;
      updates.fish_voice_prompt = fishPrefix;
      try { await apiCall('PATCH', '/api/sessions/' + state.sessionId + '/voice-profile', updates); showToast('已保存', 'success'); } catch(e) { showToast(e.message, 'error'); }
    });
  }

  // DEPRECATED: renderVoiceCastResult was for old Fish Audio public model casting.
  // Main voice flow is now ElevenLabs Voice Design via renderVoiceCandidates.
  // This function is retained for reference but not called from active UI.
  function renderVoiceCastResult(data) {
    var candidates = data.candidates || [];
    var box = document.createElement('div');
    box.className = 'voice-cast-result';
    var html = '<div class="voice-summary">音色底座候选</div>';
    if (data.strategy) html += '<div class="voice-reason">' + escapeHtml(data.strategy) + '</div>';
    if (data.warning) html += '<div class="voice-warnings">' + escapeHtml(data.warning) + '</div>';
    if (!candidates.length) {
      html += '<div class="voice-loading">暂无候选。可以在 config.yaml 增加 Fish reference_id。</div>';
    } else {
      html += '<div class="voice-candidate-list">';
      candidates.forEach(function(c, idx) {
        html += '<div class="voice-candidate">';
        html += '<div class="voice-candidate-header">';
        html += '<strong>' + (idx + 1) + '. ' + escapeHtml(c.title || c.reference_id) + '</strong>';
        html += '<button class="btn-adopt-idea voice-fav-btn" data-ref="' + escapeHtml(c.reference_id) + '" data-label="' + escapeHtml(c.title || '') + '">收藏</button>';
        html += '</div>';
        html += '<div class="voice-candidate-meta">' + escapeHtml(c.source || '') + ' · score ' + Math.round((c.score || 0) * 10) / 10 + '</div>';
        html += '<div class="voice-candidate-ref">' + escapeHtml(c.reference_id) + '</div>';
        html += '</div>';
      });
      html += '</div>';
    }
    box.innerHTML = html;
    voiceContent.appendChild(box);

    // Wire favorite buttons
    box.querySelectorAll('.voice-fav-btn').forEach(function(btn) {
      btn.addEventListener('click', async function(e) {
        e.stopPropagation();
        var refId = this.dataset.ref;
        var label = this.dataset.label;
        try {
          await apiCall('POST', '/api/voice-library/favorite', {
            reference_id: refId,
            label: label || '收藏音色',
            profile: { gender_tone: data.wanted_terms ? data.wanted_terms[0] : '' }
          });
          this.textContent = '已收藏';
          this.disabled = true;
          showToast('已加入音色库', 'success');
        } catch(e) { showToast(e.message, 'error'); }
      });
    });
  }

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

  // Load locked assets into draft panel
  async function loadDraftAssets() {
    if (!state.sessionId) return;
    try {
      var data = await apiCall('GET', '/api/sessions/' + state.sessionId + '/assets');
      var assets = data.assets || [];
      var locked = assets.filter(function(a) { return a.selected; });
      if (!locked.length) return;
      var summary = '';
      locked.forEach(function(a) {
        var label = a.asset_type === 'image_locked' ? '立绘' : a.asset_type === 'voice_identity' ? '声音' : '';
        if (label) summary += '<span class="asset-badge">' + label + '</span> ';
      });
      var el = document.getElementById('draft-assets');
      if (!el) {
        el = document.createElement('div');
        el.id = 'draft-assets';
        el.className = 'draft-assets';
        var draftContent = document.getElementById('draft-content');
        if (draftContent) draftContent.appendChild(el);
      }
      el.innerHTML = summary || '';
      el.classList.toggle('hidden', !summary);
    } catch(e) {}
  }

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
        searchResult.innerHTML = '<div class="search-error">' + escapeHtml(data.error || '未找到结果') + '</div>';
      }
    } catch (e) {
      searchResult.innerHTML = '<div class="search-error">' + escapeHtml(e.message) + '</div>';
    } finally {
      btnSearchGo.disabled = false;
    }
  }

  function renderInspirationCard(insp) {
    searchResult.innerHTML = '';
    var card = createEl('div', { className: 'inspiration-card' });
    card.appendChild(createEl('h4', { textContent: insp.title || '搜索灵感' }));
    if (insp.summary) {
      card.appendChild(createEl('div', { className: 'insp-summary', textContent: insp.summary }));
    }

    if (insp.usable_ideas && insp.usable_ideas.length > 0) {
      var list = createEl('ul', { className: 'insp-ideas' });
      insp.usable_ideas.forEach(function(idea, i) {
        var li = createEl('li');
        li.appendChild(createEl('span', { textContent: idea }));
        li.appendChild(createEl('button', {
          type: 'button',
          className: 'btn-adopt-idea',
          textContent: '采用',
          dataset: { idea: String(i) },
          on_click: function() {
            var selected = insp.usable_ideas[parseInt(this.dataset.idea)];
            searchPanel.classList.add('hidden');
            chatInput.value = '请参考这个方向来完善角色：' + selected;
            sendMessage();
          }
        }));
        list.appendChild(li);
      });
      card.appendChild(list);
    }

    if (insp.cautions && insp.cautions.length > 0) {
      card.appendChild(createEl('div', { className: 'insp-cautions', textContent: '注意: ' + insp.cautions.join('; ') }));
    }

    if (insp.sources && insp.sources.length > 0) {
      var sources = createEl('div', { className: 'insp-sources' });
      sources.appendChild(document.createTextNode('参考来源: '));
      insp.sources.forEach(function(s) {
        sources.appendChild(createEl('a', {
          href: s.url,
          target: '_blank',
          rel: 'noopener noreferrer',
          textContent: (s.title || s.url).slice(0, 30)
        }));
        sources.appendChild(document.createTextNode(' '));
      });
      card.appendChild(sources);
    }

    searchResult.appendChild(card);
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
          html += '<div class="history-item" data-query="' + escapeAttr(q.query || '') + '">';
          html += '<span class="history-query">' + escapeHtml((q.query || '').slice(0, 30)) + '</span>';
          html += '<span class="history-title-text">' + escapeHtml((inp.title || '').slice(0, 20)) + '</span>';
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

  $('#btn-register-submit').addEventListener('click', async function() {
    var u = $('#reg-username').value.trim();
    var p = $('#reg-password').value;
    if (u.length < 3) { showError(authError, '用户名至少 3 个字符'); return; }
    if (p.length < 8) { showError(authError, '密码至少 8 个字符'); return; }
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
    userStatus.innerHTML = '<span class="user-role">' + escapeHtml(label) + '</span>';
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

  async function loadFeatureFlags() {
    try {
      var features = await apiCall('GET', '/api/features');
      var voiceBtn = $('#btn-voice');
      if (voiceBtn) voiceBtn.classList.toggle('hidden', !features.voice_enabled);
    } catch (e) {
      // Keep defaults if features endpoint fails.
    }
  }

  // Check auth on load
  var authChecked = false;
  (async function checkAuth() {
    try {
      var data = await apiCall('GET', '/api/auth/me');
      updateUserDisplay(data.user);
      authChecked = true;
      authOverlay.classList.add('hidden');
      await loadFeatureFlags();
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
        this.textContent = input.type === 'password' ? '显示' : '隐藏';
      }
    });
  });
  authOverlay.addEventListener('click', function(e) {
    if (e.target === authOverlay && authChecked) hideAuth();
  });
})();
