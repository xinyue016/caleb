(function () {
  'use strict';

  var messagesEl = document.getElementById('messages');
  var form = document.getElementById('chatForm');
  var input = document.getElementById('messageInput');
  var sendBtn = document.getElementById('sendBtn');
  var resetBtn = document.getElementById('resetBtn');
  var quickRow = document.getElementById('quickRow');
  var statusPill = document.getElementById('statusPill');
  var statusText = document.getElementById('statusText');
  var providerChip = document.getElementById('providerChip');
  var chatMeta = document.getElementById('chatMeta');
  var toast = document.getElementById('toast');
  var authScreen = document.getElementById('authScreen');
  var chatWorkspace = document.getElementById('chatWorkspace');
  var authForm = document.getElementById('authForm');
  var authUsername = document.getElementById('authUsername');
  var authPassword = document.getElementById('authPassword');
  var authStatus = document.getElementById('authStatus');
  var loginBtn = document.getElementById('loginBtn');
  var registerBtn = document.getElementById('registerBtn');
  var logoutBtn = document.getElementById('logoutBtn');
  var userLabel = document.getElementById('userLabel');
  var toastTimer = null;
  var currentUser = null;

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove('show'); }, 3000);
  }

  function setStatus(mode, text) {
    statusPill.classList.remove('online', 'error');
    if (mode) statusPill.classList.add(mode);
    statusText.textContent = text;
  }

  function setAuthStatus(message, isError) {
    authStatus.textContent = message;
    authStatus.classList.toggle('error', Boolean(isError));
  }

  function createAvatar() {
    var avatar = document.createElement('div');
    avatar.className = 'avatar';
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'caleb-avatar');
    var use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', '#calebAvatar');
    svg.appendChild(use);
    avatar.appendChild(svg);
    return avatar;
  }

  function addMessage(role, text, options) {
    options = options || {};
    var article = document.createElement('article');
    article.className = 'message ' + role;
    article.appendChild(createAvatar());

    var bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text;
    article.appendChild(bubble);

    if (options.id) article.id = options.id;
    messagesEl.appendChild(article);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return article;
  }

  function addTyping() {
    var article = document.createElement('article');
    article.className = 'message assistant typing';
    article.id = 'typingMessage';
    article.appendChild(createAvatar());
    var typingBubble = document.createElement('div');
    typingBubble.className = 'bubble';
    typingBubble.textContent = '信号连接中...';
    article.appendChild(typingBubble);
    messagesEl.appendChild(article);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function removeTyping() {
    var node = document.getElementById('typingMessage');
    if (node) node.remove();
  }

  async function requestJson(url, options) {
    var response = await fetch(url, options);
    var data = {};
    try { data = await response.json(); } catch (error) { data = {}; }
    if (!response.ok) {
      var error = new Error(data.error || ('HTTP ' + response.status));
      error.status = response.status;
      throw error;
    }
    return data;
  }

  async function loadHealth() {
    try {
      var health = await requestJson('/api/health');
      setStatus('online', 'ONLINE');
      providerChip.textContent = String(health.provider || 'mock').toUpperCase();
      chatMeta.textContent = 'LOCAL MEMORY · ' + String(health.model || 'PERSONA').toUpperCase();
    } catch (error) {
      setStatus('error', 'OFFLINE');
      providerChip.textContent = 'OFFLINE';
      chatMeta.textContent = 'SERVER CONNECTION FAILED';
    }
  }

  function showAuth(message, isError) {
    currentUser = null;
    chatWorkspace.classList.add('hidden');
    authScreen.classList.remove('hidden');
    logoutBtn.disabled = true;
    userLabel.textContent = 'NOT SIGNED IN';
    setAuthStatus(message || '请登录后继续对话', Boolean(isError));
    authPassword.value = '';
  }

  async function showChat(user) {
    currentUser = user;
    authScreen.classList.add('hidden');
    chatWorkspace.classList.remove('hidden');
    logoutBtn.disabled = false;
    userLabel.textContent = user.display_name || user.username || 'USER';
    await loadHistory();
    window.setTimeout(function () { input.focus(); }, 80);
  }

  async function checkAuth() {
    try {
      var data = await requestJson('/api/me');
      if (data.authenticated && data.user) {
        await showChat(data.user);
      } else {
        showAuth('登录后会恢复你自己的聊天记录', false);
      }
    } catch (error) {
      if (error.status === 401) {
        showAuth('登录后会恢复你自己的聊天记录', false);
      } else {
        showAuth('无法连接服务器，请确认 python server.py 正在运行', true);
      }
    }
  }

  async function authenticate(endpoint, successMessage) {
    var username = authUsername.value.trim();
    var password = authPassword.value;
    if (!username || !password) {
      setAuthStatus('请输入账号和密码', true);
      return;
    }
    loginBtn.disabled = true;
    registerBtn.disabled = true;
    setAuthStatus('连接中...', false);
    try {
      var data = await requestJson(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username, password: password, display_name: username })
      });
      authPassword.value = '';
      setAuthStatus(successMessage, false);
      await showChat(data.user);
      showToast(successMessage);
    } catch (error) {
      setAuthStatus(error.message || '登录失败', true);
    } finally {
      loginBtn.disabled = false;
      registerBtn.disabled = false;
    }
  }

  async function loadHistory() {
    try {
      var data = await requestJson('/api/history?limit=60');
      var history = data.history || [];
      messagesEl.innerHTML = '';
      if (!history.length) {
        addMessage('assistant', '妹妹，我在。慢慢说，我听着。');
        return;
      }
      history.forEach(function (item) {
        addMessage(item.role === 'user' ? 'user' : 'assistant', item.content);
      });
    } catch (error) {
      messagesEl.innerHTML = '';
      addMessage('assistant', '妹妹，我在。慢慢说，我听着。');
    }
  }

  function resizeInput() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 150) + 'px';
  }

  authForm.addEventListener('submit', async function (event) {
    event.preventDefault();
    await authenticate('/api/login', '登录成功');
  });

  registerBtn.addEventListener('click', async function () {
    await authenticate('/api/register', '账号已创建');
  });

  logoutBtn.addEventListener('click', async function () {
    try {
      await fetch('/api/logout', { method: 'POST' });
    } catch (error) {
      /* The local UI still logs out even if the network request fails. */
    }
    messagesEl.innerHTML = '';
    showAuth('已退出，账号数据仍然保存在服务器', false);
  });

  input.addEventListener('input', resizeInput);
  input.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    var message = input.value.trim();
    if (!message || !currentUser) return;

    addMessage('user', message);
    input.value = '';
    resizeInput();
    sendBtn.disabled = true;
    addTyping();
    setStatus(null, 'TRANSMITTING');

    try {
      var data = await requestJson('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message, platform: 'web' })
      });
      removeTyping();
      addMessage('assistant', data.reply || '我在。');
      providerChip.textContent = String(data.provider || 'mock').toUpperCase();
      setStatus('online', 'ONLINE');
      if (data.warning) chatMeta.textContent = 'MODEL FALLBACK · CHECK .ENV';
    } catch (error) {
      removeTyping();
      addMessage('assistant', '这边信号断了。你先别急，我还在。');
      setStatus('error', 'ERROR');
      showToast('发送失败：' + error.message);
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  });

  quickRow.addEventListener('click', function (event) {
    var button = event.target.closest('button[data-prompt]');
    if (!button) return;
    input.value = button.getAttribute('data-prompt') || '';
    resizeInput();
    input.focus();
  });

  resetBtn.addEventListener('click', async function () {
    if (!window.confirm('清空当前账号的对话记录？')) return;
    try {
      await requestJson('/api/reset', { method: 'POST' });
      messagesEl.innerHTML = '';
      addMessage('assistant', '那就从这句话重新开始。你想先跟我说什么？');
      showToast('对话记录已清空');
    } catch (error) {
      showToast('清空失败：' + error.message);
    }
  });

  resizeInput();
  loadHealth();
  checkAuth();
})();
