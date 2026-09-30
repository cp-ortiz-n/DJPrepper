"""Evaluate candidate key features against the manually verified sample."""

from __future__ import annotations

import json
import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from math import gcd
from pathlib import Path

import librosa
import numpy as np
from scipy.signal import resample_poly

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helpers.analysis import _ensemble_key_estimate, _estimate_key
from helpers.audio_loader import load_audio

REFERENCES = {
    "Martin Solveig, Good Times Ahead - Intoxicated - Edit.wav": "C major",
    "Sammy Virji - If U Need It.wav": "A# minor",
    "Tove Lo, SG Lewis - HEAT.wav": "E minor",
    "La Bouche - Be My Lover.wav": "C# minor",
    "Diffrent - A Little Closer.wav": "G minor",
    "Alok, Ella Eyre, Kenny Dope, Never Dull - Deep Down (feat. Never Dull).wav": "D minor",
    "Karen Harding, Zac Samuel - Say Something - Zac Samuel Remix.wav": "G major",
    "Oliver Heldens, Becky Hill - Gecko (Overdrive).wav": "G minor",
    "A.D.O.R., Smokey Bubblin' B - Young World.wav": "E major",
}


def _analyze(row: tuple[str, str]) -> dict[str, object]:
    name, source_path = row
    audio = load_audio(Path(source_path))
    mono = librosa.to_mono(audio.samples.T)
    sample_rate = audio.sample_rate
    if sample_rate > 22_050:
        divisor = gcd(sample_rate, 22_050)
        mono = resample_poly(mono, 22_050 // divisor, sample_rate // divisor)
        sample_rate = 22_050
    magnitude = np.abs(librosa.stft(mono, hop_length=512))
    harmonic_spectrum, _ = librosa.decompose.hpss(magnitude)
    harmonic_audio = librosa.istft(harmonic_spectrum, hop_length=512, length=len(mono))
    variants = {
        "stft": librosa.feature.chroma_stft(S=magnitude ** 2, sr=sample_rate),
        "harmonic_stft": librosa.feature.chroma_stft(S=harmonic_spectrum ** 2, sr=sample_rate),
        "cqt": librosa.feature.chroma_cqt(y=mono, sr=sample_rate, hop_length=512),
        "harmonic_cqt": librosa.feature.chroma_cqt(
            y=harmonic_audio, sr=sample_rate, hop_length=512
        ),
    }
    ensemble = _ensemble_key_estimate(
        variants["stft"], variants["harmonic_stft"], variants["cqt"]
    )
    return {
        "track": name,
        "reference": REFERENCES[name],
        "ensemble": {"key": ensemble[0], "confidence": ensemble[1]},
        "variants": {
            key: {"key": result[0], "confidence": result[1]}
            for key, chroma in variants.items()
            if (result := _estimate_key(chroma))
        },
    }


def main() -> None:
    database = Path("output/reports/audioextender.sqlite3")
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT source_name, source_path FROM jobs WHERE status='complete'"
        ).fetchall()
    selected = {name: path for name, path in rows if name in REFERENCES}
    results = []
    with ProcessPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_analyze, item) for item in selected.items()]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps(result), flush=True)
    for variant in ("stft", "harmonic_stft", "cqt", "harmonic_cqt"):
        exact = sum(item["variants"][variant]["key"] == item["reference"] for item in results)
        print(f"{variant}: {exact}/{len(results)}")
    ensemble_exact = sum(item["ensemble"]["key"] == item["reference"] for item in results)
    print(f"ensemble: {ensemble_exact}/{len(results)}")


if __name__ == "__main__":
    main()
