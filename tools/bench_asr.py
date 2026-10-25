"""Benchmark local speech-to-text backends on one 16kHz wav.

Usage: python tools/bench_asr.py <audio.wav> [audio_seconds]
Prints load time, transcribe time, real-time factor (RTF = transcribe/audio),
and a text sample for each backend that's importable.
"""
import sys
import time


def _audio_seconds(path):
    import wave
    try:
        with wave.open(path) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def bench_faster_whisper(audio, model):
    from faster_whisper import WhisperModel
    t = time.time()
    m = WhisperModel(model, device="cpu", compute_type="int8")
    load = time.time() - t
    t = time.time()
    segs, _info = m.transcribe(audio, beam_size=1)
    txt = " ".join(s.text for s in segs).strip()
    return load, time.time() - t, txt


def bench_vosk(audio, model_path):
    import json
    import wave
    from vosk import Model, KaldiRecognizer
    t = time.time()
    model = Model(model_path)
    load = time.time() - t
    t = time.time()
    wf = wave.open(audio)
    rec = KaldiRecognizer(model, wf.getframerate())
    out = []
    while True:
        data = wf.readframes(4000)
        if not data:
            break
        if rec.AcceptWaveform(data):
            out.append(json.loads(rec.Result()).get("text", ""))
    out.append(json.loads(rec.FinalResult()).get("text", ""))
    return load, time.time() - t, " ".join(x for x in out if x).strip()


def main():
    audio = sys.argv[1]
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else _audio_seconds(audio)
    print(f"audio: {audio}  (~{secs:.0f}s)\n")

    for model in ("tiny.en", "base.en", "small.en"):
        try:
            load, dur, txt = bench_faster_whisper(audio, model)
            rtf = dur / secs if secs else 0
            print(f"[faster-whisper {model}]  load {load:.1f}s  transcribe {dur:.1f}s  RTF {rtf:.2f}")
            print(f"    {txt[:240]}\n")
        except Exception as e:
            print(f"[faster-whisper {model}]  unavailable: {e}\n")

    import os
    vm = os.environ.get("VOSK_MODEL")
    if vm:
        try:
            load, dur, txt = bench_vosk(audio, vm)
            rtf = dur / secs if secs else 0
            print(f"[vosk {os.path.basename(vm)}]  load {load:.1f}s  transcribe {dur:.1f}s  RTF {rtf:.2f}")
            print(f"    {txt[:240]}\n")
        except Exception as e:
            print(f"[vosk]  unavailable: {e}\n")


if __name__ == "__main__":
    main()
