# How GPS finds you — with music an AI author wrote

A one-minute science explainer (six scenes, about 89 s with Kokoro narration) whose background
music is an original **score file**, [`assets/music/time_of_flight.yaml`](assets/music/time_of_flight.yaml),
made by an AI author from a template of the built-in `momentum` bed by following the author
guide's "Making music" recipe. It plays like a bed:

```yaml
music: time_of_flight              # assets/music/time_of_flight.yaml, rendered when the video is joined
```

```
vidgen validate examples/gps-time-of-flight     # reads the score file
vidgen lint examples/gps-time-of-flight         # incl. the music_check rule on the piece
vidgen music check examples/gps-time-of-flight/assets/music/time_of_flight.yaml --out build/check
vidgen music render examples/gps-time-of-flight/assets/music/time_of_flight.yaml --out time_of_flight.mp3
vidgen tts examples/gps-time-of-flight          # Kokoro (the kokoro extra): local and free
vidgen render examples/gps-time-of-flight
```

No audio is committed. Hear a 15 s clip of the piece (the end of its build and its lift) on the
[Listen page](../../docs/music/README.md#made-with-the-score-format). The craft behind it, and
genre sketches to start from, are in [docs/COOKBOOK-MUSIC.md](../../docs/COOKBOOK-MUSIC.md).

## The piece

*Time of Flight*: B minor, 108 BPM, 4/4, 24 bars = 53.3 s, a seamless loop.

| section | bars | chords | what plays |
|---|---|---|---|
| intro | 1–4 | Bm(add9) F#m7 | dark pad, the arpeggio behind a 700 Hz filter, satellite pings with echoes |
| build | 5–12 | Bm(add9) F#m7 Gmaj7 Em9 | kick, off-beat bass and hats enter; the pad and arpeggio open; a riser in the last two bars |
| lift | 13–20 | Gmaj7 A Bm(add9) D | the pad open, a clap on 2 and 4, a soft lead with long notes in a hall |
| settle | 21–24 | Gmaj7 F#sus4 | pad and arpeggio close again to where the intro starts; the pings return |

What it kept from `momentum`: the pumping pad, a kick on every beat, the off-beat bass, the
sixteenth-note hats. What is new: key, tempo and chords; four sections with a build and a lift;
an FM-pluck arpeggio (accents 4+4+2+3+3) with a filter that opens through the build; the pings;
the lead tune.

## How it was made: the iteration log

Each version changed one thing and was checked with `vidgen music check vN.yaml --compare
v(N-1).yaml` (about 7–30 s each); the spectrograms were looked at after versions 3 and 8.

| version | change | what the check said |
|---|---|---|
| v0 | `vidgen music template momentum` | fine; G minor, 120 BPM, voice range 13 %, bass 61 % |
| v1 | key B minor, tempo 108, progression `i(add9) v7 VImaj7 iv9`, turn on `Vsus4` (the template's written G-minor voicings replaced by Roman numerals) | fine; heard B minor (97 % on the key's notes), tempo heard as 2/3 (the 3+3+2 ostinato) |
| v2 | four sections: intro 4, build 8, lift 8 (`VImaj7 VII i(add9) III`), settle 4 (`VImaj7 Vsus4`); kick and bass rest in the intro, hats in build and lift, clap in the lift, riser at the end of the build | **2 fixes**: the build does not build (−0.2 dB, −3.2 dB brighter), the lift does not lift (−0.1 dB); advice: a volume ramp or filter sweep on the pad |
| v3 | the ostinato replaced by an `fm_pluck` arpeggio (new figure, accents 4+4+2+3+3) whose `lowpass` opens 700 → 3000 Hz through the build | still 2 fixes; the arpeggio is only 2 % of the sound: the spectrogram shows the pad covering everything |
| v4 | the pad shapes the energy: −3 dB and `lowpass: 1200` in the intro, a ramp to 0 dB and 2600 Hz through the build, +1.5 dB and open in the lift, back down in the settle | **fine**: build +1.0 dB and +3.3 dB brighter, lift +2.2 dB and +7.4 dB brighter; steadiness 5.3 dB (limit 8) |
| v5 | arpeggio −8 → −2 dB | fine; arpeggio 8 % of the sound, 25 % of the voice range |
| v6 | a sparse `soft_lead` tune in the lift (long notes, reverb) | fine; the lead only 0.6 % — barely there |
| v7 | lead −4 → +3 dB | fine; lead 3 %, loudest voice-range bar −29.9 dB (limit −26), lift +10.2 dB brighter |
| v8 | a 4.8 kHz `tick` "ping" with echoes in the intro and settle | fine; ping 0 % of the sound (−29 dB peak) |
| v9 | ping +8 dB (the final piece) | fine; ping audible on the spectrogram; seam 0.46 (the ping on the loop's first step; under 1 is clean) |

What the run taught (and what changed in the guide): a template's key cannot be changed alone
(its chords are written out); only sections named `build` / `lift` are judged; a part under about
1 % of the tracks table is inaudible and needs 4–8 dB; and the arpeggio's filter sweep alone did
not register as a build while the pad held 60 % of the power — shape the loudest part first.

## The check report (final version, compared with the template)

```
Time of Flight: B minor, 108 BPM, 4/4, 24 bars = 53.3 s (a loop)
verdict: fine under narration

  ok   loudness     -28.0 LUFS integrated (vidgen plays music at -28 LUFS at volume 0)
  ok   steadiness   the 3 s loudness stays within 5.1 dB (10th to 95th percentile)
  ok   peaks        true peak -15.5 dBTP, 12.5 dB over the loudness
  ok   tempo        heard 72.1 BPM = 2/3 of the score's 108 (accents or figures grouped in threes, such as 3+3+2, make the onsets repeat in threes; the same beat, fine)
  ok   loop seam    clean: the step across it is 0.46 of the music's own biggest steps
  ok   voice range  23 % of the sound in 300 Hz-3 kHz, at most -29.9 dB in a bar: room for the voice
  ok   bass         54 % of the power under 150 Hz
  ok   highs        the highs (above 5 kHz) -44.2 dB under the whole: smooth
  ok   key          97 % of the pitched sound on the key's notes (the chroma fits B minor best, 0.85)
  ok   sections     the build builds: its second half +0.9 dB, +3.3 dB brighter
  ok   sections     the lift lifts: +2.4 dB louder and +10.2 dB brighter than the build
  ok   narration    under narration_sample.mp3 with vidgen's default ducking (12 dB): voice -21.37 LUFS, music under it -42.16 LUFS; the voice's range stands 23.8 dB over the music's

sections (LUFS; brightness = level above 2 kHz):
  intro      bars   1-4      0.0 s   -31.3 LUFS  brightness  -68.8 dB
  build      bars   5-12     8.9 s   -28.6 LUFS  brightness  -61.6 dB  build +0.9 dB, +3.3 dB brighter
  lift       bars  13-20    26.7 s   -26.3 LUFS  brightness  -51.5 dB  lift +2.4 dB, +10.2 dB brighter
  settle     bars  21-24    44.4 s   -28.7 LUFS  brightness  -63.1 dB

tracks (share of the power: all / voice range / bass / highs; peak against the mix's):
  pad          pad           52.4 %  63.2 %  35.6 %   1.8 %     -0.8 dB
  kick         kick          28.7 %   0.0 %  53.1 %   0.1 %     -8.1 dB
  clap         clap           0.0 %   0.0 %   0.0 %   0.0 %    -23.3 dB
  hat          hat            0.0 %   0.0 %   0.0 %  96.5 %    -24.5 dB
  arp          fm_pluck       8.1 %  21.6 %   0.1 %   0.0 %    -15.0 dB
  bass         synth_bass     7.7 %   1.5 %  11.3 %   0.0 %    -11.0 dB
  ping         tick           0.0 %   0.0 %   0.0 %   1.6 %    -21.1 dB
  lead         soft_lead      3.1 %  13.6 %   0.0 %   0.0 %    -15.4 dB
  riser        riser          0.0 %   0.0 %   0.0 %   0.0 %    -29.9 dB

compared with momentum.yaml (the template):
                           Time of Flight  Momentum (template)
length (s)                 53.3            48.0
loudness (LUFS)            -28.0           -28.0
steadiness (dB)            5.1             0.9
true peak (dBTP)           -15.5           -15.2
peak over loudness (dB)    12.5            12.8
tempo heard (BPM)          72.1            120.0
loop seam (x)              0.46            0.24
voice range share (%)      22%             13%
loudest voice bar (dB)     -29.9           -33.0
bass share (%)             54%             61%
highs (dB)                 -44.2           -43.5
key heard                  B minor         G minor
on the key's notes (%)     97%             92%
voice clear of music (dB)  23.8            23.3
verdict                    fine under narration  fine under narration
```

In the rendered video (1920×1080, 30 fps, 88.7 s, video and audio the same length) the mix
measured −16.0 LUFS integrated, true peak −1.8 dBTP, loudness range 3.0 LU; the piece played
from the first scene to the last, ducked 12 dB under the voice. `vidgen lint` with the real
narration: 0 errors, 0 warnings (the `music_check` rule included). The numbers say the piece
fits under a voice; whether it is *good* is for a person to hear.

## Facts

GPS satellites orbit about 20,200 km up (about thirty in service); light covers 29.98 cm per
nanosecond, so a microsecond of clock error is about 300 m; a signal from straight overhead takes
about 67 ms; a receiver needs four satellites, three for its position and one for its own clock's
error; the satellites' clocks gain about 38 µs a day (+45 from weaker gravity, −7 from their
speed), about 11 km of range a day uncorrected, so they are set slightly slow before launch.
