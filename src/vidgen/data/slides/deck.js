/* vidgen slides (DESIGN.md §55): navigation, notes, overview, fullscreen and the narrated play mode. */
(function () {
  "use strict";
  var data = JSON.parse(document.getElementById("deck-data").textContent);
  var deck = document.getElementById("deck");
  var stage = document.getElementById("stage");
  var slides = Array.prototype.slice.call(stage.querySelectorAll(".slide"));
  var count = slides.length;
  var counter = document.getElementById("counter");
  var where = document.getElementById("where");
  var live = document.getElementById("live");
  var notesPanel = document.getElementById("notes-panel");
  var overview = document.getElementById("overview");
  var help = document.getElementById("help");
  var jump = document.getElementById("jump");
  var playButton = document.getElementById("btn-play");
  var notesButton = document.getElementById("btn-notes");
  var index = -1;
  var typed = "";
  var typedTimer = 0;
  var idleTimer = 0;

  function store(key, value) {
    try { window.localStorage.setItem("vidgen-slides:" + key, value); } catch (e) { /* no storage */ }
  }
  function stored(key) {
    try { return window.localStorage.getItem("vidgen-slides:" + key); } catch (e) { return null; }
  }
  function clamp(i) { return Math.max(0, Math.min(count - 1, i)); }
  function slideImage(i) { return slides[i].querySelector("img"); }

  /* ----- showing a slide ----- */
  function go(i, fromPlayer) {
    i = clamp(i);
    if (i === index) { return; }
    if (index >= 0) { slides[index].hidden = true; slides[index].classList.remove("enter"); }
    index = i;
    var slide = slides[i];
    slide.hidden = false;
    slide.classList.add("enter");
    var info = data.slides[i];
    counter.textContent = (i + 1) + " / " + count;
    where.textContent = info.where;
    live.textContent = "Slide " + (i + 1) + " of " + count + (info.where ? ", " + info.where : "");
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, "", "#" + (i + 1));
    }
    showNotes();
    if (player.playing && !fromPlayer) { player.seek(info.at); }
  }
  function next() { go(index + 1); }
  function prev() { go(index - 1); }

  function fromHash() {
    var n = parseInt(window.location.hash.replace(/^#/, ""), 10);
    return isNaN(n) ? 0 : n - 1;
  }

  /* ----- speaker notes ----- */
  function notesOn() { return !notesPanel.hidden; }
  function setNotes(on) {
    notesPanel.hidden = !on;
    deck.classList.toggle("with-notes", on);
    notesButton.setAttribute("aria-pressed", on ? "true" : "false");
    store("notes", on ? "1" : "0");
    showNotes();
  }
  function showNotes() {
    if (!notesOn() || index < 0) { return; }
    var source = slides[index].querySelector(".notes");
    notesPanel.innerHTML = source.innerHTML;
    if (index + 1 < count) {
      var nextBox = document.createElement("div");
      nextBox.className = "next";
      nextBox.textContent = "Next: " + (index + 2) + " / " + count;
      var img = document.createElement("img");
      img.src = slideImage(index + 1).src;
      img.alt = "";
      nextBox.appendChild(img);
      notesPanel.appendChild(nextBox);
    }
    notesPanel.scrollTop = 0;
  }

  /* ----- overview and help ----- */
  function openLayer(layer) {
    closeLayers();
    layer.hidden = false;
    var focus = layer.querySelector(".thumb.current") || layer.querySelector("button");
    if (focus) { focus.focus(); }
  }
  function closeLayers() {
    var wasOpen = !overview.hidden || !help.hidden;
    overview.hidden = true;
    help.hidden = true;
    if (wasOpen) { stage.focus(); }
    return wasOpen;
  }
  function toggleOverview() {
    if (!overview.hidden) { closeLayers(); return; }
    var thumbs = overview.querySelectorAll(".thumb");
    for (var t = 0; t < thumbs.length; t++) {
      var img = thumbs[t].querySelector("img");
      if (!img.getAttribute("src")) { img.src = slideImage(t).src; }
      thumbs[t].classList.toggle("current", t === index);
      if (t === index) { thumbs[t].setAttribute("aria-current", "true"); } else { thumbs[t].removeAttribute("aria-current"); }
    }
    openLayer(overview);
  }
  function toggleHelp() {
    if (!help.hidden) { closeLayers(); } else { openLayer(help); }
  }
  overview.addEventListener("click", function (event) {
    var thumb = event.target.closest(".thumb");
    if (thumb) { closeLayers(); go(parseInt(thumb.getAttribute("data-index"), 10)); }
  });

  /* ----- fullscreen ----- */
  function toggleFullscreen() {
    var root = document.documentElement;
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else if (root.requestFullscreen) {
      root.requestFullscreen().catch(function () { /* refused */ });
    }
  }
  function wake() {
    deck.classList.remove("idle");
    window.clearTimeout(idleTimer);
    if (document.fullscreenElement) {
      idleTimer = window.setTimeout(function () { deck.classList.add("idle"); }, 2500);
    }
  }
  document.addEventListener("fullscreenchange", wake);
  document.addEventListener("mousemove", wake);

  /* ----- narrated play mode: the slides follow the deck timeline, the beats' audio plays on it ----- */
  var player = {
    playing: false,
    position: 0,
    started: 0,
    origin: 0,
    clip: null,
    frame: 0,
    audio: function (clip) { return clip ? document.getElementById(clip.id) : null; },
    now: function () {
      return this.playing ? this.origin + (performance.now() - this.started) / 1000 : this.position;
    },
    seek: function (t) {
      this.origin = t;
      this.started = performance.now();
      this.position = t;
      this.sync(true);
    },
    sync: function (force) {
      var t = this.now();
      var current = null;
      for (var c = 0; c < data.clips.length; c++) {
        var clip = data.clips[c];
        if (t >= clip.at && t < clip.at + clip.duration) { current = clip; break; }
      }
      if (current !== this.clip) {
        var old = this.audio(this.clip);
        if (old) { old.pause(); }
        this.clip = current;
        force = true;
      }
      var audio = this.audio(current);
      if (audio && this.playing) {
        var want = t - current.at;
        if (force || Math.abs(audio.currentTime - want) > 0.3) {
          try { audio.currentTime = want; } catch (e) { /* not seekable yet */ }
        }
        if (audio.paused) { var p = audio.play(); if (p && p.catch) { p.catch(function () { /* blocked */ }); } }
      }
    },
    tick: function () {
      if (!player.playing) { return; }
      var t = player.now();
      if (t >= data.duration) { player.stop(); go(count - 1, true); return; }
      var target = index;
      while (target + 1 < count && data.slides[target + 1].at <= t) { target++; }
      while (target > 0 && data.slides[target].at > t) { target--; }
      if (target !== index) { go(target, true); }
      player.sync(false);
      player.frame = window.requestAnimationFrame(player.tick);
    },
    start: function () {
      if (count === 0) { return; }
      this.playing = true;
      var info = data.slides[index];
      var t = this.position;
      if (t < info.at || t >= info.until) { t = info.at; }
      this.seek(t);
      playButton.setAttribute("aria-pressed", "true");
      playButton.querySelector(".label").textContent = "Pause";
      this.frame = window.requestAnimationFrame(this.tick);
    },
    stop: function () {
      this.position = this.now();
      this.playing = false;
      window.cancelAnimationFrame(this.frame);
      var audio = this.audio(this.clip);
      if (audio) { audio.pause(); }
      this.clip = null;
      playButton.setAttribute("aria-pressed", "false");
      playButton.querySelector(".label").textContent = "Play";
    },
    toggle: function () { if (this.playing) { this.stop(); } else { this.start(); } }
  };

  /* ----- input ----- */
  function typeDigit(d) {
    typed = (typed + d).slice(-5);
    jump.textContent = "Go to " + typed;
    jump.hidden = false;
    window.clearTimeout(typedTimer);
    typedTimer = window.setTimeout(clearTyped, 2500);
  }
  function clearTyped() { typed = ""; jump.hidden = true; }

  document.addEventListener("keydown", function (event) {
    if (event.ctrlKey || event.metaKey || event.altKey) { return; }
    var key = event.key;
    var layerOpen = !overview.hidden || !help.hidden;
    if (layerOpen) {
      if (key === "Escape" || (key === "o" || key === "O") && !overview.hidden || key === "?" && !help.hidden) {
        closeLayers(); event.preventDefault();
      }
      return;
    }
    var target = event.target;
    if (target && target.tagName === "BUTTON" && (key === "Enter" || key === " ") && !typed) { return; }
    if (/^[0-9]$/.test(key)) { typeDigit(key); event.preventDefault(); return; }
    if (key === "Enter" && typed) { var n = parseInt(typed, 10); clearTyped(); go(n - 1); event.preventDefault(); return; }
    if (key === "Escape" && typed) { clearTyped(); return; }
    if (key === "Backspace" && typed) { typed = typed.slice(0, -1); if (typed) { typeDigit(""); } else { clearTyped(); } event.preventDefault(); return; }
    switch (key) {
      case "ArrowRight": case "ArrowDown": case "PageDown": case "Enter": next(); break;
      case " ": if (event.shiftKey) { prev(); } else { next(); } break;
      case "ArrowLeft": case "ArrowUp": case "PageUp": case "Backspace": prev(); break;
      case "Home": go(0); break;
      case "End": go(count - 1); break;
      case "s": case "S": case "n": case "N": setNotes(!notesOn()); break;
      case "o": case "O": case "g": case "G": toggleOverview(); break;
      case "f": case "F": toggleFullscreen(); break;
      case "p": case "P": case "k": case "K": player.toggle(); break;
      case "?": case "h": case "H": toggleHelp(); break;
      case "Escape": if (player.playing) { player.stop(); } break;
      default: return;
    }
    event.preventDefault();
  });

  var swipe = null;
  var swiped = false;
  stage.addEventListener("pointerdown", function (event) { swipe = { x: event.clientX, y: event.clientY }; swiped = false; });
  stage.addEventListener("pointerup", function (event) {
    if (!swipe) { return; }
    var dx = event.clientX - swipe.x;
    var dy = event.clientY - swipe.y;
    swipe = null;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) {
      swiped = true;
      if (dx < 0) { next(); } else { prev(); }
    }
  });
  stage.addEventListener("click", function (event) {
    if (swiped) { swiped = false; return; }
    var box = stage.getBoundingClientRect();
    if (event.clientX - box.left < box.width / 3) { prev(); } else { next(); }
  });

  function bind(id, action) {
    document.getElementById(id).addEventListener("click", function () { action(); });
  }
  bind("btn-prev", prev);
  bind("btn-next", next);
  bind("btn-play", function () { player.toggle(); });
  bind("btn-notes", function () { setNotes(!notesOn()); });
  bind("btn-overview", toggleOverview);
  bind("btn-fullscreen", toggleFullscreen);
  bind("btn-help", toggleHelp);
  bind("btn-close-overview", closeLayers);
  bind("btn-close-help", closeLayers);

  window.addEventListener("hashchange", function () { go(fromHash()); });

  if (count === 0) { counter.textContent = "0 / 0"; return; }
  if (stored("notes") === "1") { setNotes(true); }
  go(fromHash());
  window.vidgenSlides = {
    go: go, next: next, prev: prev, player: player,
    get index() { return index; },
    get count() { return count; }
  };
})();
