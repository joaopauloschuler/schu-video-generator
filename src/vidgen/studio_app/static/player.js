// Playback of rendered audio (DESIGN.md §94.6, §94.14): <audio> elements streaming the server's
// WAV with range requests, so seeking works. The browser never synthesises sound itself.
//
// Times given to and reported by the player are the piece's (from its start). A source may be
// a section cut from the piece: `offset` is where that section starts, so its local time
// `t` is the piece's `offset + t` (DESIGN.md §94.12, loops of one section).
//
// A new source while playing (a re-render, a mute, "under narration", A/B) is loaded in a second
// element, seeked a little ahead of the moment playing, started when the playing one gets there
// and cross-faded over FADE_SECONDS: the music goes on at the same moment with no gap. The
// element playing always has the id "audio".

const FADE_SECONDS = 0.06;
const LEAD_SECONDS = 0.15;   // how far ahead the new source is seeked (its loading time)
const LATE_TRIES = 3;        // seeks ahead again when loading took longer; then it just switches

export class Player {
  constructor(audio, onTick, onState) {
    this.audio = audio;
    this.spare = document.createElement("audio");
    this.spare.preload = "auto";
    this.spare.id = "audio-next";
    audio.after(this.spare);
    this.onTick = onTick;
    this.onState = onState;
    this.url = null;
    this.offset = 0;
    this.frame = 0;
    this.swap = null;   // the source being brought in while the other plays
    this.swaps = 0;     // swaps done without a gap (tests read it)
    for (const el of [audio, this.spare]) {
      const mine = (fn) => () => { if (el === this.audio) fn(); };
      el.addEventListener("play", mine(() => { this.onState(true); this.tick(); }));
      el.addEventListener("pause", mine(() => { if (!this.swap?.started) this.onState(false); }));
      el.addEventListener("ended", mine(() => { this.onState(false); this.onTick(this.time); }));
      el.addEventListener("seeked", mine(() => this.onTick(this.time)));
      el.addEventListener("loadedmetadata", mine(() => this.onTick(this.time)));
    }
  }

  get playing() { return !this.audio.paused && !this.audio.ended; }
  // the length of the source playing (a section's, when looping one)
  get duration() { return Number.isFinite(this.audio.duration) ? this.audio.duration : 0; }
  // the moment of the piece playing
  get time() { return this.offset + this.audio.currentTime; }
  // a source is still being brought in
  get switching() { return this.swap !== null; }

  // Play `url` from now on. `at`: the moment of the piece to continue from (default: the one
  // playing), kept when it falls inside the new source, else its start; playing goes on if it was.
  setSource(url, { loop = false, offset = 0, at = null } = {}) {
    this.cancelSwap();
    if (url === this.url && offset === this.offset) {
      this.audio.loop = Boolean(loop);
      if (at !== null) this.seek(at);
      return;
    }
    if (this.playing && at === null) this.bringIn(url, Boolean(loop), offset);
    else this.load(url, Boolean(loop), offset, at ?? (this.url ? this.time : 0));
  }

  // Switch the playing element to `url` at once (stopped, a seek, or a swap that cannot wait).
  load(url, loop, offset, moment) {
    const wasPlaying = this.playing;
    this.url = url;
    this.offset = offset;
    this.audio.loop = loop;
    this.audio.src = url;
    this.audio.load();
    const local = moment - offset;
    this.audio.addEventListener("loadedmetadata", () => {
      this.audio.currentTime = local > 0 && local < this.duration ? local : 0;
      this.onTick(this.time);
      if (wasPlaying) this.play();
    }, { once: true });
  }

  // Bring `url` in while the current source plays on (see the header).
  bringIn(url, loop, offset) {
    const next = this.spare;
    const swap = { url, loop, offset, next, tries: 0, started: false, target: 0 };
    this.swap = swap;
    document.body.dataset.switching = "1"; // tests and screenshots wait on it
    next.loop = loop;
    next.volume = 0;
    next.src = url;
    next.load();
    const aim = () => {
      if (this.swap !== swap) return;
      const local = this.time + LEAD_SECONDS - offset;
      const duration = Number.isFinite(next.duration) ? next.duration : 0;
      if (!(local > 0 && local < duration - LEAD_SECONDS) || swap.tries++ >= LATE_TRIES) {
        // outside the new source (a section after the moment), or loading too slow: switch now
        this.finishSwap(swap, Math.min(Math.max(this.time - offset, 0), Math.max(duration - 0.01, 0)), true);
        return;
      }
      swap.target = offset + local;
      next.currentTime = local;
      next.addEventListener("seeked", wait, { once: true });
    };
    const wait = () => {
      if (this.swap !== swap) return;
      const step = () => {
        if (this.swap !== swap) return;
        if (!this.playing) return this.finishSwap(swap, this.time - offset, true);
        const now = this.time;
        if (now >= swap.target - 0.008) return this.startSwap(swap);
        if (now < swap.target - LEAD_SECONDS - 1) return aim(); // the old source wrapped round its loop
        swap.frame = requestAnimationFrame(step);
      };
      if (this.time > swap.target) aim(); // it took longer than the lead: aim again
      else step();
    };
    next.addEventListener("loadedmetadata", aim, { once: true });
  }

  startSwap(swap) {
    swap.started = true;
    const old = this.audio;
    const next = swap.next;
    next.play().then(() => {
      if (this.swap !== swap) return;
      // how far apart the two sources are when the fade starts (ms; tests and the report read it)
      document.body.dataset.swapDrift = String(Math.round(1000 * (swap.offset + next.currentTime - this.time)));
      const begin = performance.now();
      const fade = () => {
        if (this.swap !== swap) return;
        const k = Math.min(1, (performance.now() - begin) / (FADE_SECONDS * 1000));
        next.volume = k;
        old.volume = 1 - k;
        if (k < 1) swap.frame = requestAnimationFrame(fade);
        else this.finishSwap(swap, null, false);
      };
      fade();
    }).catch(() => this.finishSwap(swap, this.time - swap.offset, true));
  }

  // Make the swap's element the playing one. `local`: where to put it (null: where it plays).
  finishSwap(swap, local, hard) {
    if (this.swap !== swap) return;
    const old = this.audio;
    const next = swap.next;
    const wasPlaying = !old.paused || swap.started;
    cancelAnimationFrame(swap.frame);
    this.swap = null;
    delete document.body.dataset.switching;
    old.pause();
    old.volume = 1;
    next.volume = 1;
    if (local !== null) next.currentTime = Math.max(0, local);
    old.id = "audio-next";
    next.id = "audio";
    this.audio = next;
    this.spare = old;
    this.url = swap.url;
    this.offset = swap.offset;
    if (!hard) document.body.dataset.swaps = String(++this.swaps);
    if (wasPlaying && next.paused) this.play();
    else if (wasPlaying) { this.onState(true); this.tick(); }
    old.removeAttribute("src");
    old.load();
    this.onTick(this.time);
  }

  cancelSwap() {
    const swap = this.swap;
    if (!swap) return;
    cancelAnimationFrame(swap.frame);
    this.swap = null;
    delete document.body.dataset.switching;
    swap.next.pause();
    swap.next.volume = 1;
    this.audio.volume = 1;
    if (swap.started) this.onState(this.playing);
  }

  play() {
    if (!this.url) return Promise.resolve();
    return this.audio.play().catch(() => this.onState(false));
  }

  pause() {
    this.cancelSwap();
    this.audio.pause();
  }

  stop() {
    this.cancelSwap();
    this.audio.pause();
    if (this.url) this.audio.currentTime = 0;
    this.onTick(this.time);
  }

  // Go to moment `seconds` of the piece (inside the source playing). A source being brought in
  // is switched to at once.
  seek(seconds) {
    if (this.swap) {
      const swap = this.swap;
      this.finishSwap(swap, seconds - swap.offset, true);
    }
    if (!this.url) return;
    const local = seconds - this.offset;
    this.audio.currentTime = Math.max(0, Math.min(local, this.duration || local));
    this.onTick(this.time);
  }

  tick() {
    cancelAnimationFrame(this.frame);
    const step = () => {
      this.onTick(this.time);
      if (this.playing) this.frame = requestAnimationFrame(step);
    };
    this.frame = requestAnimationFrame(step);
  }
}
