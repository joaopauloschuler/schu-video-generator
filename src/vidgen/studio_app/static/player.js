// Playback of rendered audio (DESIGN.md §94.6): an <audio> element streaming the server's WAV
// with range requests, so seeking works. The browser never synthesises sound itself.
//
// Times given to and reported by the player are the piece's (from its start). A source may be
// a section cut from the piece: `offset` is where that section starts, so its local time
// `t` is the piece's `offset + t` (DESIGN.md §94.12, loops of one section).

export class Player {
  constructor(audio, onTick, onState) {
    this.audio = audio;
    this.onTick = onTick;
    this.onState = onState;
    this.url = null;
    this.offset = 0;
    this.frame = 0;
    audio.addEventListener("play", () => { this.onState(true); this.tick(); });
    audio.addEventListener("pause", () => this.onState(false));
    audio.addEventListener("ended", () => { this.onState(false); this.onTick(this.time); });
    audio.addEventListener("seeked", () => this.onTick(this.time));
    audio.addEventListener("loadedmetadata", () => this.onTick(this.time));
  }

  get playing() { return !this.audio.paused && !this.audio.ended; }
  // the length of the source playing (a section's, when looping one)
  get duration() { return Number.isFinite(this.audio.duration) ? this.audio.duration : 0; }
  // the moment of the piece playing
  get time() { return this.offset + this.audio.currentTime; }

  // Play `url` from now on. `at`: the moment of the piece to continue from (default: the one
  // playing), kept when it falls inside the new source, else its start; playing goes on if it was.
  setSource(url, { loop = false, offset = 0, at = null } = {}) {
    const moment = at ?? (this.url ? this.time : 0);
    const wasPlaying = this.playing;
    this.audio.loop = Boolean(loop);
    if (url === this.url && offset === this.offset) {
      if (at !== null) this.seek(at);
      return;
    }
    this.url = url;
    this.offset = offset;
    this.audio.src = url;
    this.audio.load();
    const local = moment - offset;
    this.audio.addEventListener("loadedmetadata", () => {
      this.audio.currentTime = local > 0 && local < this.duration ? local : 0;
      this.onTick(this.time);
      if (wasPlaying) this.play();
    }, { once: true });
  }

  play() {
    if (!this.url) return Promise.resolve();
    return this.audio.play().catch(() => this.onState(false));
  }

  pause() { this.audio.pause(); }

  stop() {
    this.audio.pause();
    if (this.url) this.audio.currentTime = 0;
    this.onTick(this.time);
  }

  // Go to moment `seconds` of the piece (inside the source playing).
  seek(seconds) {
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
