/* Aynur PWA 客户端：按住说话 → 服务端 → 文字 + 语音。 */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const LS = window.localStorage;

  const state = {
    sessionId: ensureSession(),
    lastAudioUrl: null,
    lastResult: null,
    recorder: null,
    recording: false,
    mode: 'demo',
    startedAt: 0,
  };

  const TEXT = {
    idle: 'بېسىپ سۆزلەڭ · 按住说话',
    recording: 'ئاڭلاۋاتىمەن… · 我在听',
    thinking: 'ئويلىنىۋاتىمەن… · 我在想',
    error: 'كەچۈرۈڭ، قايتا سىناڭ · 出错了',
    short: 'بىر ئاز ئۇزۇنراق سۆزلەڭ · 再多说一会儿',
    denied: 'مىكروفونغا رۇخسەت بېرىڭ · 请允许麦克风',
    done: 'بېسىپ سۆزلەڭ · 按住说话',
  };

  // ---------- 会话 ----------
  function ensureSession() {
    let id = LS.getItem('aynur.session');
    if (!id) {
      id = 's' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
      LS.setItem('aynur.session', id);
    }
    return id;
  }

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  // ---------- 录音 ----------
  class MicRecorder {
    constructor() {
      this.ctx = null;
      this.stream = null;
      this.node = null;
      this.source = null;
      this.buffers = [];
      this.rate = 48000;
    }

    get active() {
      return !!this.ctx;
    }

    async start() {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      const Ctx = window.AudioContext || window.webkitAudioContext;
      const ctx = new Ctx();
      this.stream = stream;
      this.ctx = ctx;
      this.rate = ctx.sampleRate;
      this.buffers = [];
      const source = ctx.createMediaStreamSource(stream);
      const node = ctx.createScriptProcessor(2048, 1, 1);
      node.onaudioprocess = (event) => {
        if (!this.ctx) return;
        this.buffers.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      };
      source.connect(node);
      node.connect(ctx.destination);
      this.source = source;
      this.node = node;
    }

    async stop() {
      const rate = this.rate;
      const buffers = this.buffers.slice();
      this.release();
      if (!buffers.length) return null;
      const merged = mergeBuffers(buffers);
      if (merged.length < rate * 0.35) return null;
      const pcm = downsample(merged, rate, 16000);
      return encodeWav(pcm, 16000);
    }

    release() {
      try { this.node && this.node.disconnect(); } catch (_) {}
      try { this.source && this.source.disconnect(); } catch (_) {}
      try { this.stream && this.stream.getTracks().forEach((t) => t.stop()); } catch (_) {}
      try { this.ctx && this.ctx.close(); } catch (_) {}
      this.ctx = null;
      this.stream = null;
      this.node = null;
      this.source = null;
      this.buffers = [];
    }
  }

  function mergeBuffers(buffers) {
    let total = 0;
    for (const b of buffers) total += b.length;
    const out = new Float32Array(total);
    let offset = 0;
    for (const b of buffers) {
      out.set(b, offset);
      offset += b.length;
    }
    return out;
  }

  function downsample(input, inRate, outRate) {
    if (outRate >= inRate) return input;
    const ratio = inRate / outRate;
    const length = Math.floor(input.length / ratio);
    const out = new Float32Array(length);
    for (let i = 0; i < length; i += 1) {
      const start = Math.floor(i * ratio);
      const end = Math.min(Math.floor((i + 1) * ratio), input.length);
      let sum = 0;
      for (let j = start; j < end; j += 1) sum += input[j];
      out[i] = sum / Math.max(1, end - start);
    }
    return out;
  }

  function encodeWav(samples, sampleRate) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const write = (offset, text) => {
      for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
    };
    write(0, 'RIFF');
    view.setUint32(4, 36 + samples.length * 2, true);
    write(8, 'WAVE');
    write(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    write(36, 'data');
    view.setUint32(40, samples.length * 2, true);
    let offset = 44;
    for (let i = 0; i < samples.length; i += 1) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      offset += 2;
    }
    return new Blob([view], { type: 'audio/wav' });
  }

  // ---------- 界面 ----------
  function setStatus(key, extra) {
    const el = $('status');
    el.textContent = extra || TEXT[key] || TEXT.idle;
    el.classList.toggle('recording', key === 'recording');
    el.classList.toggle('thinking', key === 'thinking');
  }

  function show(id, visible) {
    $(id).classList.toggle('hidden', !visible);
  }

  function renderResult(data) {
    state.lastResult = data;
    state.lastAudioUrl = data.audio_url || null;
    const greeting = document.querySelector('.greeting');
    if (greeting) greeting.classList.add('faded');

    if (data.transcript_ug) {
      show('transcriptCard', true);
      $('transcript').textContent = data.transcript_ug;
      $('transcriptZh').textContent = data.transcript_zh || '';
    }
    show('replyCard', true);
    $('reply').textContent = data.reply_ug || '';
    $('replyZh').textContent = data.reply_zh || '';

    show('replay', false);
    show('askFamily', true);

    if (data.audio_url) {
      play(data.audio_url);
    } else {
      fetchSpeech(data);
    }
  }

  async function fetchSpeech(data) {
    try {
      const res = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text_ug: data.reply_ug || '',
          text_zh: data.reply_zh || '',
        }),
      });
      if (!res.ok || res.status === 204) {
        setStatus('idle');
        return;
      }
      const blob = await res.blob();
      if (!blob.size) {
        setStatus('idle');
        return;
      }
      state.lastAudioUrl = URL.createObjectURL(blob);
      show('replay', true);
      play(state.lastAudioUrl);
    } catch (err) {
      console.error(err);
      setStatus('idle');
    }
  }

  function play(url) {
    try {
      const audio = new Audio(url);
      audio.addEventListener('ended', () => setStatus('idle'));
      const promise = audio.play();
      if (promise && promise.catch) {
        promise.catch(() => {
          setStatus('idle', 'يەنە ئاڭلاڭ · 点"再听一遍"播放');
        });
      }
    } catch (_) {
      setStatus('idle');
    }
  }

  async function sendAudio(blob) {
    setStatus('thinking');
    const form = new FormData();
    form.append('audio', blob, 'turn.wav');
    form.append('session_id', state.sessionId);
    try {
      const res = await fetch('/api/turn', { method: 'POST', body: form });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      renderResult(data);
      if (data.latency_ms && data.latency_ms.total) {
        console.info('[aynur] turn', data.latency_ms, data.arm, data.mode);
      }
    } catch (err) {
      console.error(err);
      setStatus('error');
    }
  }

  async function sendText(text) {
    setStatus('thinking');
    const form = new FormData();
    form.append('text', text);
    form.append('session_id', state.sessionId);
    try {
      const res = await fetch('/api/turn', { method: 'POST', body: form });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      renderResult(await res.json());
    } catch (err) {
      console.error(err);
      setStatus('error');
    }
  }

  // ---------- 按住说话 ----------
  async function startTalk(event) {
    if (event && event.cancelable) event.preventDefault();
    if (state.recording) return;
    state.recording = true;
    $('talk').classList.add('recording');
    setStatus('recording');
    state.startedAt = Date.now();
    try {
      state.recorder = new MicRecorder();
      await state.recorder.start();
    } catch (err) {
      console.error(err);
      state.recording = false;
      $('talk').classList.remove('recording');
      state.recorder = null;
      setStatus('denied');
    }
  }

  async function stopTalk(event) {
    if (event && event.cancelable) event.preventDefault();
    if (!state.recording) return;
    state.recording = false;
    $('talk').classList.remove('recording');

    const recorder = state.recorder;
    state.recorder = null;
    if (!recorder) {
      setStatus('idle');
      return;
    }
    const elapsed = Date.now() - state.startedAt;
    const blob = await recorder.stop();
    if (!blob) {
      setStatus(elapsed < 400 ? 'short' : 'idle');
      return;
    }
    await sendAudio(blob);
  }

  function bindTalk() {
    const talk = $('talk');
    talk.addEventListener('pointerdown', startTalk);
    talk.addEventListener('pointerup', stopTalk);
    talk.addEventListener('pointercancel', stopTalk);
    talk.addEventListener('pointerleave', (event) => {
      if (state.recording) stopTalk(event);
    });
    talk.addEventListener('contextmenu', (event) => event.preventDefault());
    talk.addEventListener('keydown', (event) => {
      if (event.code === 'Space' && !event.repeat) {
        event.preventDefault();
        startTalk();
      }
    });
    talk.addEventListener('keyup', (event) => {
      if (event.code === 'Space') {
        event.preventDefault();
        stopTalk();
      }
    });
  }

  // ---------- 设置 ----------
  let pressTimer = null;

  function bindSettings() {
    const avatar = $('avatar');
    const armTimer = () => {
      pressTimer = setTimeout(openSettings, 1800);
    };
    const clearTimer = () => {
      clearTimeout(pressTimer);
      pressTimer = null;
    };
    avatar.addEventListener('pointerdown', armTimer);
    ['pointerup', 'pointerleave', 'pointercancel'].forEach((ev) =>
      avatar.addEventListener(ev, clearTimer)
    );
    $('openSettings').addEventListener('click', openSettings);
    $('closeSettings').addEventListener('click', closeSettings);
    $('sheet').addEventListener('click', (event) => {
      if (event.target === $('sheet')) closeSettings();
    });

    $('saveSettings').addEventListener('click', saveSettings);
    $('exportBtn').addEventListener('click', () => {
      window.location.href = '/api/export';
    });
    $('failuresBtn').addEventListener('click', loadFailures);
    $('resetMemory').addEventListener('click', resetMemory);
    $('testBtn').addEventListener('click', () => {
      const text = $('f_test').value.trim();
      if (text) sendText(text);
    });
  }

  async function openSettings() {
    $('sheet').classList.remove('hidden');
    await Promise.all([loadSettings(), loadProfile()]);
  }

  function closeSettings() {
    $('sheet').classList.add('hidden');
  }

  async function loadSettings() {
    try {
      const data = await fetch('/api/settings').then((r) => r.json());
      $('f_mode').value = data.mode || 'auto';
      $('f_arm').value = data.arm || "A'";
      $('f_limit').value = data.daily_limit ?? 60;
      $('f_llm_url').value = data.llm_base_url || '';
      $('f_llm_model').value = data.llm_model || '';
      $('f_llm_key').value = data.llm_api_key || '';
      $('f_tts_url').value = data.tts_url || '';
      $('f_tts_voice').value = data.tts_voice_ug || '';
      $('f_asr').value = `${data.resolved_asr} / TTS: ${data.resolved_tts}`;
      $('statusLine').textContent = `模式：${data.resolved_mode} · 链路：${data.arm} · LLM：${
        data.has_llm ? '已配置' : '未配置'
      } · 维语 TTS：${data.has_ug_voice ? '已配置' : '未配置（演示用中文音）'}`;
    } catch (err) {
      console.error(err);
    }
  }

  async function loadProfile() {
    try {
      const data = await fetch('/api/profile').then((r) => r.json());
      $('f_title').value = data.title || '';
      $('f_city').value = data.city || '';
      $('f_age').value = data.age || '';
      $('f_health').value = data.health || '';
      $('f_family').value = data.family || '';
    } catch (err) {
      console.error(err);
    }
  }

  async function saveSettings() {
    const profile = {
      title: $('f_title').value.trim(),
      city: $('f_city').value.trim(),
      age: $('f_age').value.trim(),
      health: $('f_health').value.trim(),
      family: $('f_family').value.trim(),
    };
    const settings = {
      mode: $('f_mode').value,
      arm: $('f_arm').value,
      daily_limit: Number($('f_limit').value) || 60,
      llm_base_url: $('f_llm_url').value.trim(),
      llm_model: $('f_llm_model').value.trim(),
      llm_api_key: $('f_llm_key').value.trim(),
      tts_url: $('f_tts_url').value.trim(),
      tts_voice_ug: $('f_tts_voice').value.trim(),
    };
    try {
      await fetch('/api/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profile),
      });
      const updated = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      }).then((r) => r.json());
      $('statusLine').textContent = `已保存 · 模式 ${updated.resolved_mode} · TTS ${updated.resolved_tts}`;
      setStatus('idle');
      refreshBadge();
    } catch (err) {
      console.error(err);
      $('statusLine').textContent = '保存失败：' + err.message;
    }
  }

  async function loadFailures() {
    const log = $('log');
    log.hidden = false;
    try {
      const data = await fetch('/api/failures?limit=30').then((r) => r.json());
      log.textContent =
        data.items.length === 0
          ? '暂无失败记录。'
          : data.items
              .map((it) => `${it.created_at}  [${it.reason}]\n  ${it.text}`)
              .join('\n\n');
    } catch (err) {
      log.textContent = '读取失败：' + err.message;
    }
  }

  async function resetMemory() {
    if (!window.confirm('清空长期档案（称呼、健康、家里的事）？这个不能撤销。')) return;
    await fetch('/api/profile/reset', { method: 'POST' });
    await loadProfile();
    $('statusLine').textContent = '长期档案已清空。';
  }

  // ---------- 反馈 ----------
  function bindFeedback() {
    $('replay').addEventListener('click', () => {
      if (state.lastAudioUrl) play(state.lastAudioUrl);
    });
    $('askFamily').addEventListener('click', () => sendFeedback('ask_family'));
  }

  async function sendFeedback(reason) {
    const text = state.lastResult ? state.lastResult.transcript_ug || '' : '';
    try {
      await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: state.sessionId, reason, text }),
      });
      setStatus('idle', 'ئائىلىڭىزگە ئېيتىپ قويدۇم · 已经记下来告诉家里人');
    } catch (err) {
      console.error(err);
    }
  }

  // ---------- 启动 ----------
  async function refreshBadge() {
    try {
      const data = await fetch('/api/health').then((r) => r.json());
      state.mode = data.mode;
      const badge = $('badge');
      badge.textContent =
        data.mode === 'demo'
          ? '演示模式 · 未配置模型'
          : `在线 · ${data.arm} · ASR ${data.asr}`;
      badge.classList.toggle('live', data.mode === 'live');
    } catch (err) {
      console.error(err);
    }
  }

  async function bootGreeting() {
    const key = 'aynur.greeting.v2.' + today();
    let text = LS.getItem(key);
    if (!text) {
      try {
        const data = await fetch('/api/greeting', { method: 'POST' }).then((r) => r.json());
        text = data.text_ug;
        if (text) LS.setItem(key, text);
      } catch (err) {
        console.error(err);
      }
    }
    if (text) $('greeting').textContent = text;
  }

  async function boot() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setStatus('denied');
    }
    bindTalk();
    bindSettings();
    bindFeedback();
    await refreshBadge();
    await bootGreeting();
    setStatus('idle');

    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    }

    // 仅用于截图/联调的开发钩子
    const query = location.search;
    if (query.includes('sheet')) setTimeout(openSettings, 400);
    if (query.includes('demo')) {
      setTimeout(() => sendText('باشىم ئاغرىۋاتىدۇ، نېمە قىلسام بولىدۇ؟'), 700);
    }
  }

  document.addEventListener('DOMContentLoaded', boot);
  document.addEventListener('contextmenu', (event) => {
    if (event.target.closest('#talk')) event.preventDefault();
  });
})();
