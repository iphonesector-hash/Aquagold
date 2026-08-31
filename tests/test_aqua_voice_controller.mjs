import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';


const python = readFileSync(new URL('../aqua_voice_injector.py', import.meta.url), 'utf8');
const match = python.match(/VOICE_UI_JS = r"""([\s\S]*?)"""\n\n\n@app_v3\.app\.get/);
assert.ok(match, 'canonical Aqua voice JavaScript was not found');
const controllerSource = match[1];


function controllerHarness({api} = {}) {
  const spoken = [];
  class Utterance {
    constructor(text) {
      this.text = text;
      this.lang = '';
      this.voice = null;
      this.rate = 1;
      this.pitch = 1;
      this.volume = 1;
    }
  }
  const synthesis = {
    voices: [{name: 'Dariush', lang: 'fa-IR', voiceURI: 'com.apple.voice.compact.fa-IR.Dariush'}],
    addEventListener() {},
    cancel() {},
    getVoices() { return this.voices; },
    resume() {},
    speak(utterance) {
      spoken.push(utterance);
      setTimeout(() => {
        utterance.onstart?.();
        utterance.onend?.();
      }, 0);
    },
  };
  const base = {
    aquaSettings: {auto_speak: false},
    aquaMessages: [],
    aquaInput: '',
    aquaBusy: false,
    aquaSpeaking: false,
    aquaHistory() { return []; },
    aquaScroll() {},
    api: api || (async () => ({answer: 'پاسخ آریا'})),
    cookie() { return ''; },
    toast() {},
  };
  const document = {
    hidden: false,
    head: {appendChild() {}},
    addEventListener() {},
    createElement() { return {}; },
    querySelector() { return null; },
  };
  const window = {
    app: () => base,
    addEventListener() {},
    speechSynthesis: synthesis,
    SpeechSynthesisUtterance: Utterance,
  };
  const context = vm.createContext({
    Blob,
    FormData,
    Promise,
    clearTimeout,
    console,
    document,
    navigator: {},
    setTimeout,
    window,
  });
  vm.runInContext(controllerSource, context);
  return {app: context.window.app(), spoken};
}


test('a transcript is auto-submitted exactly once', async () => {
  let calls = 0;
  const {app} = controllerHarness({api: async () => { calls += 1; return {answer: 'باشه'}; }});
  app.aquaSettings.auto_speak = false;
  app.aquaVoiceSeq = 7;
  assert.equal(await app.submitAquaVoiceTranscript('سلام آریا', 7), true);
  assert.equal(await app.submitAquaVoiceTranscript('سلام آریا', 7), false);
  assert.equal(calls, 1);
  assert.equal(app.aquaVoiceCommittedRun, 7);
});


test('a transient send lock is awaited before voice auto-send', async () => {
  let calls = 0;
  const {app} = controllerHarness({api: async () => { calls += 1; return {answer: 'انجام شد'}; }});
  app.aquaSettings.auto_speak = false;
  app.aquaVoiceSeq = 3;
  app.aquaSendLock = true;
  setTimeout(() => { app.aquaSendLock = false; }, 80);
  assert.equal(await app.submitAquaVoiceTranscript('پیام صوتی', 3), true);
  assert.equal(calls, 1);
});


test('failed voice send keeps the transcript for a manual retry', async () => {
  const {app} = controllerHarness({api: async () => { throw new Error('network failed'); }});
  app.aquaSettings.auto_speak = false;
  app.aquaVoiceSeq = 4;
  assert.equal(await app.submitAquaVoiceTranscript('متن حفظ شود', 4), false);
  assert.equal(app.aquaInput, 'متن حفظ شود');
});


test('send primes system speech and speaks with Dariush', async () => {
  const {app, spoken} = controllerHarness();
  assert.equal(app.aquaSettings.auto_speak, true);
  assert.equal(await app.sendAqua('تست صدا'), true);
  await new Promise(resolve => setTimeout(resolve, 20));
  const audible = spoken.find(item => item.volume === 1 && item.text === 'پاسخ آریا');
  assert.ok(audible);
  assert.equal(audible.voice?.name, 'Dariush');
  assert.equal(audible.lang, 'fa-IR');
});


test('a second send cannot duplicate an in-flight request', async () => {
  let release;
  let calls = 0;
  const gate = new Promise(resolve => { release = resolve; });
  const {app} = controllerHarness({api: async () => { calls += 1; await gate; return {answer: 'تمام'}; }});
  app.aquaSettings.auto_speak = false;
  const first = app.sendAqua('یک پیام');
  const second = await app.sendAqua('یک پیام');
  assert.equal(second, false);
  assert.equal(calls, 1);
  release();
  assert.equal(await first, true);
});
