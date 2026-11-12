// vidgen's control of the page's own animations (DESIGN.md §118.8): CSS animations and
// transitions and the Web Animations API, SVG (SMIL) animation and <video> elements are held
// still by vidgen and set to the clock's time before each screenshot. A fragment joined after
// clock.js (it uses clock).

// ----- Web Animations (CSS animations and transitions are Animations too) ---------------------

const animationApi = {};
for (const name of ['play', 'pause', 'reverse', 'finish', 'cancel', 'updatePlaybackRate']) animationApi[name] = Animation.prototype[name];
for (const name of ['currentTime', 'playbackRate', 'playState']) animationApi[name] = Object.getOwnPropertyDescriptor(Animation.prototype, name);
const nativeState = (a) => animationApi.playState.get.call(a);
const nativeTime = (a) => animationApi.currentTime.get.call(a);
const setNativeTime = (a, ms) => animationApi.currentTime.set.call(a, ms);

// Animation -> {t: its time in ms when the clock was at `at`, at, playing, finished}
const animations = new Map();

function trackAnimation(a) {
  let record = animations.get(a);
  if (record !== undefined) return record;
  const state = nativeState(a);
  // A running animation starts at 0 now; Chromium's own time for it is real time, so unused.
  record = { t: state === 'paused' ? (nativeTime(a) ?? 0) : 0, at: clock.now(), playing: state === 'running', finished: state === 'finished' };
  if (state === 'finished') record.t = nativeTime(a) ?? 0;
  animations.set(a, record);
  if (record.playing) animationApi.pause.call(a);   // a CSS animation paused by its CSS stays so
  return record;
}

function advanceRecord(a, record) {
  if (record.playing && !record.finished) record.t += (clock.now() - record.at) * animationApi.playbackRate.get.call(a);
  record.at = clock.now();
}

function effectEnd(a) {
  return a.effect ? a.effect.getComputedTiming().endTime : 0;
}

// Sets one animation to the clock's time; finishes it (its `finished` promise and `finish`
// event) once a playing one passes its end.
function placeAnimation(a, record) {
  const state = nativeState(a);
  if (state === 'idle') { animations.delete(a); return; }
  if (record.finished) return;
  if (state === 'running' && !record.playing) {   // resumed by its CSS (animation-play-state)
    record.playing = true;
    record.at = clock.now();
  }
  advanceRecord(a, record);
  const rate = animationApi.playbackRate.get.call(a);
  if (record.playing && ((rate > 0 && record.t >= effectEnd(a)) || (rate < 0 && record.t <= 0))) {
    record.finished = true;
    animationApi.finish.call(a);
    return;
  }
  if (state === 'running') animationApi.pause.call(a);
  setNativeTime(a, record.t);
}

function wrapAnimation(name, body) {
  Object.defineProperty(Animation.prototype, name, { value: body, writable: true, configurable: true });
}

// The page's calls are followed in the clock's time: the animation stays paused in Chromium.
wrapAnimation('play', function play() {
  const record = trackAnimation(this);
  placeAnimation(this, record);
  record.finished = false;
  animationApi.play.call(this);   // rewinds a finished animation, as the browser does
  record.t = nativeTime(this) ?? 0;
  record.at = clock.now();
  record.playing = true;
  animationApi.pause.call(this);
});
wrapAnimation('pause', function pause() {
  const record = trackAnimation(this);
  placeAnimation(this, record);
  record.playing = false;
  record.finished = false;
  animationApi.pause.call(this);
});
wrapAnimation('reverse', function reverse() {
  const record = trackAnimation(this);
  placeAnimation(this, record);
  record.finished = false;
  animationApi.reverse.call(this);
  record.t = nativeTime(this) ?? 0;
  record.at = clock.now();
  record.playing = true;
  animationApi.pause.call(this);
});
wrapAnimation('finish', function finish() {
  const record = trackAnimation(this);
  animationApi.finish.call(this);
  record.t = nativeTime(this) ?? 0;
  record.finished = true;
});
wrapAnimation('cancel', function cancel() {
  animations.delete(this);
  animationApi.cancel.call(this);
});
wrapAnimation('updatePlaybackRate', function updatePlaybackRate(rate) {
  const record = trackAnimation(this);
  advanceRecord(this, record);
  animationApi.playbackRate.set.call(this, rate);
});
Object.defineProperty(Animation.prototype, 'currentTime', {
  get() {
    const record = animations.get(this);
    if (record === undefined || record.finished) return nativeTime(this);
    return record.t + (record.playing ? (clock.now() - record.at) * animationApi.playbackRate.get.call(this) : 0);
  },
  set(ms) {
    const record = trackAnimation(this);
    setNativeTime(this, ms);
    record.t = nativeTime(this) ?? 0;
    record.at = clock.now();
    record.finished = false;
  },
  configurable: true,
});
Object.defineProperty(Animation.prototype, 'playbackRate', {
  get() { return animationApi.playbackRate.get.call(this); },
  set(rate) {
    const record = trackAnimation(this);
    advanceRecord(this, record);
    animationApi.playbackRate.set.call(this, rate);
  },
  configurable: true,
});
Object.defineProperty(Animation.prototype, 'playState', {
  get() {
    const record = animations.get(this);
    if (record === undefined || record.finished) return nativeState(this);
    return nativeState(this) === 'idle' ? 'idle' : (record.playing ? 'running' : 'paused');
  },
  configurable: true,
});

// ----- SVG (SMIL) ------------------------------------------------------------------------------

const svgs = new Map();   // outermost <svg> -> the clock's time when vidgen first saw it

// ----- <video> ---------------------------------------------------------------------------------

const mediaApi = {
  play: HTMLMediaElement.prototype.play,
  pause: HTMLMediaElement.prototype.pause,
  currentTime: Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'currentTime'),
  paused: Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'paused'),
};
const videos = new Map();   // <video> -> {t: its time in ms when the clock was at `at`, at, playing}

function trackVideo(video) {
  let record = videos.get(video);
  if (record !== undefined) return record;
  record = { t: 0, at: clock.now(), playing: video.autoplay || !mediaApi.paused.get.call(video) };
  video.autoplay = false;   // Chromium must not start it on its own
  mediaApi.pause.call(video);
  videos.set(video, record);
  return record;
}

function videoSeconds(video, record) {
  if (record.playing) record.t += (clock.now() - record.at) * video.playbackRate;
  record.at = clock.now();
  const duration = video.duration;
  let seconds = Math.max(0, record.t / 1000);
  if (Number.isFinite(duration) && duration > 0) seconds = video.loop ? seconds % duration : Math.min(seconds, duration);
  return seconds;
}

const isVideo = (element) => element instanceof HTMLVideoElement;
for (const [name, body] of Object.entries({
  play() { if (!isVideo(this)) return mediaApi.play.call(this); videoSeconds(this, trackVideo(this)); trackVideo(this).playing = true; return Promise.resolve(); },
  pause() { if (!isVideo(this)) return mediaApi.pause.call(this); const record = trackVideo(this); videoSeconds(this, record); record.playing = false; return undefined; },
})) Object.defineProperty(HTMLMediaElement.prototype, name, { value: body, writable: true, configurable: true });
Object.defineProperty(HTMLMediaElement.prototype, 'paused', {
  get() { return isVideo(this) ? !trackVideo(this).playing : mediaApi.paused.get.call(this); }, configurable: true,
});
Object.defineProperty(HTMLMediaElement.prototype, 'currentTime', {
  get() {
    if (!isVideo(this)) return mediaApi.currentTime.get.call(this);
    const record = trackVideo(this);
    return Math.max(0, (record.t + (record.playing ? (clock.now() - record.at) * this.playbackRate : 0)) / 1000);
  },
  set(seconds) {
    if (!isVideo(this)) { mediaApi.currentTime.set.call(this, seconds); return; }
    const record = trackVideo(this);
    record.t = Number(seconds) * 1000;
    record.at = clock.now();
    mediaApi.currentTime.set.call(this, seconds);
  },
  configurable: true,
});

// A video is ready to be shown when it has the picture at its time, or cannot (an error, no source).
const videoReady = (video) => video.error !== null || video.networkState === HTMLMediaElement.NETWORK_NO_SOURCE
  || (!video.seeking && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA);

function whenReady(video) {
  if (videoReady(video)) return Promise.resolve();
  return new Promise((resolve) => {
    const check = () => {
      if (!videoReady(video)) return;
      for (const name of events) video.removeEventListener(name, check);
      resolve();
    };
    const events = ['seeked', 'loadeddata', 'canplay', 'error', 'emptied', 'stalled'];
    for (const name of events) video.addEventListener(name, check);
  });
}

// ----- all of it -------------------------------------------------------------------------------

// Starts following what the page created since the last call (style is computed now, so CSS
// animations and transitions a change of class just started are among them).
function discoverMedia() {
  for (const a of document.getAnimations()) trackAnimation(a);
  for (const svg of document.querySelectorAll('svg')) {
    if (svg.ownerSVGElement === null && !svgs.has(svg)) {
      svgs.set(svg, clock.now());
      svg.pauseAnimations();
    }
  }
  for (const video of document.querySelectorAll('video')) trackVideo(video);
}

// Sets every animation, SVG and video to the clock's time, then waits for the videos' pictures.
async function placeMedia() {
  discoverMedia();
  for (const [a, record] of animations) placeAnimation(a, record);
  for (const [svg, since] of svgs) {
    if (!svg.isConnected) { svgs.delete(svg); continue; }
    svg.setCurrentTime((clock.now() - since) / 1000);
  }
  const waits = [];
  for (const [video, record] of videos) {   // also one not in the page (drawn on a canvas)
    const seconds = videoSeconds(video, record);
    if (Math.abs(mediaApi.currentTime.get.call(video) - seconds) > 1e-6) mediaApi.currentTime.set.call(video, seconds);
    waits.push(whenReady(video));
  }
  await Promise.all(waits);
}

// Waits for the pictures of the page's <img> elements (a broken one is skipped).
async function decodeImages() {
  await Promise.all([...document.images].filter((img) => !img.complete).map((img) => img.decode().catch(() => undefined)));
}

const media = { discoverMedia, placeMedia, decodeImages };
