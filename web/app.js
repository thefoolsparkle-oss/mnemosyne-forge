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
        assetSection = document.createElement('div');
        assetSection.id = 'card-assets-section';
        assetSection.className = 'card-section';
        assetSection.innerHTML = '<h4>绑定资产</h4><div id="card-assets"></div>';
        var cardBody = document.querySelector('.card-body');
        if (cardBody) cardBody.appendChild(assetSection);
      }
      var assetsEl = document.getElementById('card-assets');
      var assetHtml = '';
      if (selectedAssets.image) {
        var img = selectedAssets.image;
        var imgName = (img.path || '').split(/[/\\]/).pop();
        var meta = img.metadata_json ? (typeof img.metadata_json === 'string' ? JSON.parse(img.metadata_json) : img.metadata_json) : (img.metadata || {});
        assetHtml += '<div class="card-asset-item"><strong>立绘</strong><br>';
        if (imgName) assetHtml += '<img src="/exports/images/' + imgName + '" style="max-width:120px;border-radius:6px;margin:4px 0">';
        if (meta.prompt) assetHtml += '<span style="font-size:11px;color:var(--text-muted)">' + escapeHtml((meta.prompt || '').slice(0, 80)) + '</span>';
        assetHtml += '</div>';
      }
      if (selectedAssets.voice_identity) {
        var v = selectedAssets.voice_identity;
        var vMeta = v.metadata_json ? (typeof v.metadata_json === 'string' ? JSON.parse(v.metadata_json) : v.metadata_json) : (v.metadata || {});
        var voiceName = vMeta.voice_name || (v.path || '').slice(0, 16);
        var voiceId = (v.path || '').split(/[/\\]/).pop() || voiceName;
        assetHtml += '<div class="card-asset-item"><strong>声音</strong><br>';
        assetHtml += '<span style="font-size:11px">' + escapeHtml(voiceName) + ' (' + escapeHtml(voiceId.slice(0, 12)) + '...)</span>';
        assetHtml += '</div>';
      }
      if (selectedAssets.voice_audio) {
        var aName = (selectedAssets.voice_audio.path || '').split(/[/\\]/).pop();
        assetHtml += '<audio controls src="/exports/voices/' + aName + '" style="width:100%;margin-top:4px"></audio>';
      }
      assetsEl.innerHTML = assetHtml || '<p style="color:var(--text-muted)">暂无绑定资产</p>';
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
        var div = document.createElement('div');
        div.className = 'library-item';
        div.dataset.sessionId = s.id;
        var name = s.title || '未命名';
        var concept = s.core_concept || '';
        var score = Math.round((s.completion_score || 0) * 100);
        var date = new Date(s.updated_at).toLocaleDateString('zh-CN');
        div.innerHTML =
          '<div class="library-item-avatar">' + escapeHtml(name[0] || '?') + '</div>' +
          '<div class="library-item-info">' +
            '<div class="library-item-name">' + escapeHtml(name) + '</div>' +
            '<div class="library-item-concept">' + escapeHtml(concept || '无描述') + '</div>' +
          '</div>' +
          '<div class="library-item-meta">' +
            '<div class="library-item-score">' + score + '%</div>' +
            '<div class="library-item-date">' + escapeHtml(date) + '</div>' +
          '</div>' +
          '<button class="library-item-del" data-sid="' + escapeAttr(s.id) + '">&times;</button>';
        div.querySelector('.library-item-del').addEventListener('click', function(e) {
          e.stopPropagation();
          deleteSession(s.id, name);
        });
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
    assetOverlay.addEventListener('click', function(e) {
      if (e.target === assetOverlay) assetOverlay.classList.add('hidden');
    });
  }

  function renderAssets(assets) {
    if (!assets.length) {
      assetContent.innerHTML = '<div class="asset-empty">还没有生成资产。</div>';
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
    var html = '';
    keys.forEach(function(type) {
      html += '<section class="asset-section"><h4>' + escapeHtml(assetTypeLabel(type)) + '</h4><div class="asset-grid">';
      grouped[type].forEach(function(asset) {
        var meta = asset.metadata || {};
        var url = assetDisplayUrl(asset);
        html += '<article class="asset-card' + (asset.selected ? ' selected' : '') + '">';
        if (url && type.indexOf('image_') === 0) html += '<img class="asset-thumb" src="' + escapeAttr(url) + '" alt="">';
        if (url && type.indexOf('voice_') === 0) html += '<audio controls src="' + escapeAttr(url) + '"></audio>';
        html += '<div class="asset-meta">';
        html += '<strong>' + escapeHtml(meta.label || assetTypeLabel(type)) + '</strong>';
        html += '<span>' + escapeHtml(asset.provider || '') + '</span>';
        if (asset.created_at) html += '<span>' + escapeHtml(new Date(asset.created_at).toLocaleString('zh-CN')) + '</span>';
        if (asset.selected) html += '<em>已选中</em>';
        html += '</div><div class="asset-actions">';
        if (type === 'image_locked') {
          html += '<button type="button" class="btn-adopt-idea asset-variation-image" data-id="' + escapeAttr(asset.id) + '">生成变体</button>';
        } else if (type === 'image_candidate') {
          html += '<button type="button" class="btn-adopt-idea asset-lock-image" data-id="' + escapeAttr(asset.id) + '" data-style="' + escapeAttr(meta.style || '') + '" data-prompt="' + escapeAttr(meta.prompt || '') + '">锁定为 canon</button>';
        } else {
          html += '<button type="button" class="btn-adopt-idea asset-select" data-id="' + escapeAttr(asset.id) + '" data-type="' + escapeAttr(type) + '">选中</button>';
        }
        html += '</div></article>';
      });
      html += '</div></section>';
    });
    assetContent.innerHTML = html;
    wireExclusiveAudio(assetContent);

    assetContent.querySelectorAll('.asset-lock-image').forEach(function(btn) {
      btn.addEventListener('click', async function() {
        try {
          var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/visual-canon-lock', {
            asset_id: Number(this.dataset.id),
            style: this.dataset.style || '',
            prompt: this.dataset.prompt || '',
          });
          showToast(data.ok ? '已锁定视觉 canon' : '锁定失败', data.ok ? 'success' : 'error');
          await loadAssets();
        } catch(e) { showToast(e.message, 'error'); }
      });
    });
    assetContent.querySelectorAll('.asset-variation-image').forEach(function(btn) {
      btn.addEventListener('click', async function() {
        try {
          ensureImageOverlay();
          imageOverlay.classList.remove('hidden');
          imageContent.innerHTML = '<div class="image-loading">正在基于已锁定立绘生成一致性变体…</div>';
          var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/image-variations', {});
          renderImageCandidates(data.candidates || []);
          await loadAssets();
        } catch(e) { showToast(e.message, 'error'); }
      });
    });
    assetContent.querySelectorAll('.asset-select').forEach(function(btn) {
      btn.addEventListener('click', async function() {
        try {
          await apiCall('POST', '/api/sessions/' + state.sessionId + '/assets/' + this.dataset.id + '/select', { asset_type: this.dataset.type || '' });
          showToast('已选中资产', 'success');
          await loadAssets();
        } catch(e) { showToast(e.message, 'error'); }
      });
    });
  }

  async function loadAssets() {
    if (!state.sessionId) return;
    ensureAssetOverlay();
    assetContent.innerHTML = '<div class="asset-loading">正在读取资产…</div>';
    var data = await apiCall('GET', '/api/sessions/' + state.sessionId + '/assets');
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

  function ensureImageOverlay() {
    if (imageOverlay) return;
    imageOverlay = document.createElement('div');
    imageOverlay.className = 'image-overlay hidden';
    imageOverlay.innerHTML =
      '<div class="image-panel">' +
        '<div class="image-panel-header">' +
          '<h3>立绘候选</h3>' +
          '<button type="button" class="btn-close-card" id="btn-image-close">&times;</button>' +
        '</div>' +
        '<div id="image-content" class="image-content"></div>' +
      '</div>';
    document.body.appendChild(imageOverlay);
    imageContent = imageOverlay.querySelector('#image-content');
    imageOverlay.querySelector('#btn-image-close').addEventListener('click', function() {
      imageOverlay.classList.add('hidden');
    });
    imageOverlay.addEventListener('click', function(e) {
      if (e.target === imageOverlay) imageOverlay.classList.add('hidden');
    });
  }

  function renderImageCandidates(candidates) {
    if (!candidates.length) {
      imageContent.innerHTML = '<div class="image-empty">没有生成可用候选。</div>';
      return;
    }
    var html = '<div class="image-candidate-grid">';
    candidates.forEach(function(c) {
      html += '<div class="image-candidate">';
      html += '<div class="image-candidate-title">' + escapeHtml(c.label || ('候选 ' + c.index)) + '</div>';
      if (c.image_url) {
        html += '<img src="' + escapeAttr(c.image_url) + '" alt="' + escapeAttr(c.label || 'image candidate') + '">';
        if (c.critique && c.critique.overall_score) {
          html += '<div class="image-critique">评分: ' + Math.round(c.critique.overall_score) + '/10';
          if (c.critique.passed === false) html += ' <span style="color:var(--error)">未通过</span>';
          html += '</div>';
        }
      } else {
        html += '<div class="image-error">';
        html += '<strong>' + escapeHtml(c.label || '生成失败') + '</strong><br>';
        html += escapeHtml(c.error || '未知错误') + '<br>';
        html += '<button class="btn-adopt-idea image-retry-btn" data-style="' + escapeAttr(c.style || '') + '" data-prompt="' + escapeAttr(c.prompt || '') + '" data-neg-prompt="' + escapeAttr(c.negative_prompt || '') + '">重试此风格</button>';
        html += '</div>';
      }
      html += '<div class="image-candidate-actions">';
      if (c.asset_id) {
        html += '<button type="button" class="btn-adopt-idea image-lock-btn" data-asset="' + escapeAttr(c.asset_id) + '" data-style="' + escapeAttr(c.style || '') + '" data-prompt="' + escapeAttr(c.prompt || '') + '">锁定</button>';
      }
      if (c.prompt) {
        html += '<button type="button" class="btn-adopt-idea image-copy-btn" data-prompt="' + escapeAttr(c.prompt) + '">复制 Prompt</button>';
      }
      html += '</div></div>';
    });
    html += '</div>';
    imageContent.innerHTML = html;

    imageContent.querySelectorAll('.image-lock-btn').forEach(function(btn) {
      btn.addEventListener('click', async function() {
        try {
          var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/visual-canon-lock', {
            asset_id: Number(this.dataset.asset),
            style: this.dataset.style || '',
            prompt: this.dataset.prompt || '',
          });
          showToast(data.ok ? '已锁定角色视觉 canon' : '锁定失败', data.ok ? 'success' : 'error');
        } catch(e) { showToast(e.message, 'error'); }
      });
    });
    imageContent.querySelectorAll('.image-retry-btn').forEach(function(btn) {
      btn.addEventListener('click', async function() {
        var style = this.dataset.style;
        var prompt = this.dataset.prompt;
        var negPrompt = this.dataset['neg-prompt'] || this.dataset.negPrompt || '';
        showToast('正在重试「' + escapeHtml(style) + '」风格……', 'success');
        try {
          var retryBody = { retry_style: style };
          if (prompt) { retryBody.retry_prompt = prompt; retryBody.retry_negative_prompt = negPrompt; }
          var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/image-candidates', retryBody);
          renderImageCandidates(data.candidates || []);
        } catch(e) { showToast(e.message, 'error'); }
      });
    });
    imageContent.querySelectorAll('.image-copy-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        navigator.clipboard.writeText(this.dataset.prompt || '').then(function() {
          showToast('Prompt 已复制', 'success');
        }).catch(function() {
          showToast('复制失败', 'error');
        });
      });
    });
  }

  $('#btn-image').addEventListener('click', async function() {
    if (!state.sessionId) return;
    ensureImageOverlay();
    imageOverlay.classList.remove('hidden');
    imageContent.innerHTML = '<div class="image-loading">正在生成三张候选立绘…</div>';
    try {
      var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/image-candidates', {});
      renderImageCandidates(data.candidates || []);
    } catch(e) {
      imageContent.innerHTML = '<div class="image-error">' + escapeHtml(e.message) + '</div>';
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
    var isVoiceIdentity = provider === 'elevenlabs';
    var html = '<div class="voice-candidate-list">';
    html += '<div class="voice-summary">' + (isVoiceIdentity ? '三候选音色对比' : '表现参数对比') + '</div>';
    candidates.forEach(function(c) {
      html += '<div class="voice-candidate">';
      html += '<div class="voice-candidate-header"><strong>' + escapeHtml(c.label || ('候选 ' + c.index)) + '</strong>';
      if (c.generated_voice_id) html += '<button class="btn-adopt-idea voice-select-candidate" data-index="' + escapeAttr(c.index || '') + '" data-generated="' + escapeAttr(c.generated_voice_id) + '">选择</button>';
      html += '</div>';
      if (c.audio_url) html += '<audio controls src="' + escapeAttr(c.audio_url) + '" style="width:100%;margin-top:4px"></audio>';
      else if (c.error) html += '<div class="voice-loading" style="color:var(--error)">' + escapeHtml(c.error) + '</div>';
      html += '</div>';
    });
    html += '</div>';
    voiceContent.innerHTML = html;
    wireExclusiveAudio(voiceContent);
    voiceContent.querySelectorAll('.voice-select-candidate').forEach(function(btn) {
      btn.addEventListener('click', async function() {
        try {
          var data = await apiCall('POST', '/api/sessions/' + state.sessionId + '/voice-sample-candidates/select', { index: Number(this.dataset.index || 1), generated_voice_id: this.dataset.generated || '' });
          if (data.voice_profile) renderVoiceProfile(data.voice_profile);
          showToast('已保存这个角色音色', 'success');
        } catch(e) { showToast(e.message, 'error'); }
      });
    });
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
    var html = '<div class="inspiration-card">';
    html += '<h4>' + escapeHtml(insp.title || '搜索灵感') + '</h4>';
    if (insp.summary) html += '<div class="insp-summary">' + escapeHtml(insp.summary) + '</div>';
    if (insp.usable_ideas && insp.usable_ideas.length > 0) {
      html += '<ul class="insp-ideas">';
      insp.usable_ideas.forEach(function(idea, i) {
        html += '<li><span>' + escapeHtml(idea) + '</span><button class="btn-adopt-idea" data-idea="' + i + '">采用</button></li>';
      });
      html += '</ul>';
    }
    if (insp.cautions && insp.cautions.length > 0) {
      html += '<div class="insp-cautions">注意: ' + escapeHtml(insp.cautions.join('; ')) + '</div>';
    }
    if (insp.sources && insp.sources.length > 0) {
      html += '<div class="insp-sources">参考来源: ';
      insp.sources.forEach(function(s) {
        html += '<a href="' + escapeAttr(s.url) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml((s.title || s.url).slice(0, 30)) + '</a> ';
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

  // Check auth on load
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
        this.textContent = input.type === 'password' ? '显示' : '隐藏';
      }
    });
  });
  authOverlay.addEventListener('click', function(e) {
    if (e.target === authOverlay && authChecked) hideAuth();
  });
})();
