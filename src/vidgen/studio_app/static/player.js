// Playback of rendered audio (DESIGN.md §94.6): an <audio> element streaming the server's WAV
// with range requests, so seeking works. The browser never synthesises sound itself.

export class Player {
  constructor(audio, onTick, onState) {
    this.audio = audio;
    this.onTick = onTick;
    this.onState = onState;
    this.url = null;
    this.frame = 0;
    audio.addEventListener("play", () => { this.onState(true); this.tick(); });
    audio.addEventListener("pause", () => this.onState(false));
    audio.addEventListener("ended", () => { this.onState(false); this.onTick(this.audio.currentTime); });
    audio.addEventListener("seeked", () => this.onTick(this.audio.currentTime));
    audio.addEventListener("loadedmetadata", () => this.onTick(this.audio.currentTime));
  }

  get playing() { return !this.audio.paused && !this.audio.ended; }
  get duration() { return Number.isFinite(this.audio.duration) ? this.audio.duration : 0; }
  get time() { return this.audio.currentTime; }

  // Play `url` from now on, at the same moment if it was playing (a new render of the same piece).
  setSource(url, loop) {
    this.audio.loop = Boolean(loop);
    if (url === this.url) return;
    const at = this.audio.currentTime;
    const wasPlaying = this.playing;
    this.url = url;
    this.audio.src = url;
    this.audio.load();
    if (at > 0) {
      this.audio.addEventListener("loadedmetadata", () => {
        this.audio.currentTime = Math.min(at, this.duration);
        if (wasPlaying) this.play();
      }, { once: true });
    } else if (wasPlaying) {
      this.play();
    }
  }

  play() {
    if (!this.url) return Promise.resolve();
    return this.audio.play().catch(() => this.onState(false));
  }

  pause() { this.audio.pause(); }

  stop() {
    this.audio.pause();
    this.audio.currentTime = 0;
    this.onTick(0);
  }

  seek(seconds) {
    if (!this.url) return;
    this.audio.currentTime = Math.max(0, Math.min(seconds, this.duration || seconds));
    this.onTick(this.audio.currentTime);
  }

  tick() {
    cancelAnimationFrame(this.frame);
    const step = () => {
      this.onTick(this.audio.currentTime);
      if (this.playing) this.frame = requestAnimationFrame(step);
    };
    this.frame = requestAnimationFrame(step);
  }
}
