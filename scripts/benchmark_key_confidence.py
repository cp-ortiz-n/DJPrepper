"""Compare stored key results with the current analyzer on recent library tracks."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helpers.analysis import analyze_track
from helpers.audio_loader import load_audio
from helpers.config import EditConfig


def _analyze(row: tuple[int, str, str, str, float]) -> dict[str, object]:
    job_id, name, source_path, old_key, old_confidence = row
    started = time.monotonic()
    analysis = analyze_track(
        load_audio(Path(source_path)),
        EditConfig(cache_enabled=False, analysis_only=True),
    )
    return {
        "job_id": job_id,
        "track": name,
        "old_key": old_key,
        "old_confidence": float(old_confidence) * 100.0,
        "new_key": analysis.key_label,
        "new_confidence": analysis.key_confidence,
        "seconds": time.monotonic() - started,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--workers", type=int, default=2)
    arguments = parser.parse_args()

    with sqlite3.connect(arguments.database) as connection:
        rows = connection.execute(
            """
            SELECT idx.job_id, idx.source_name, jobs.source_path,
                   json_extract(idx.analysis_json, '$.key'),
                   json_extract(idx.analysis_json, '$.key_confidence')
            FROM library_search_index idx
            JOIN jobs ON jobs.id = idx.job_id
            WHERE jobs.status = 'complete'
              AND jobs.source_path != ''
              AND json_extract(idx.analysis_json, '$.key_confidence') IS NOT NULL
            ORDER BY idx.updated_at DESC
            LIMIT ?
            """,
            (arguments.count,),
        ).fetchall()

    results: list[dict[str, object]] = []
    with ProcessPoolExecutor(max_workers=arguments.workers) as executor:
        futures = [executor.submit(_analyze, row) for row in rows]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps(result), flush=True)

    results.sort(key=lambda item: int(item["job_id"]), reverse=True)
    old_average = sum(float(item["old_confidence"]) for item in results) / len(results)
    new_average = sum(float(item["new_confidence"]) for item in results) / len(results)
    changed_keys = sum(item["old_key"] != item["new_key"] for item in results)
    print(json.dumps({
        "summary": {
            "tracks": len(results),
            "old_average": old_average,
            "new_average": new_average,
            "confidence_delta": new_average - old_average,
            "changed_keys": changed_keys,
        },
        "results": results,
    }))


if __name__ == "__main__":
    main()
