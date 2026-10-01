from __future__ import annotations

import unittest
from unittest.mock import Mock

import numpy as np

from audioextender.analysis.dj_readiness import detect_dj_readiness


class DJReadinessTests(unittest.TestCase):
    def analysis(self, safe_bars: int, total: int = 10) -> Mock:
        frame_times = np.arange(total * 4, dtype=float)
        rms = np.full(total * 4, 0.04)
        percussion = np.full(total * 4, 0.05)
        rms[:safe_bars * 4] = 0.30
        percussion[:safe_bars * 4] = 0.24
        return Mock(
            bar_boundaries=np.arange(0, (total + 1) * 4, 4, dtype=float),
            bar_grid_confidence=np.full(total, 0.9),
            frame_times=frame_times,
            rms=rms,
            percussion_rms=percussion,
            bar_section_labels=np.asarray(
                ["intro"] * total, dtype="<U8"
            ),
        )

    def test_counts_consecutive_mixable_opening_bars(self) -> None:
        decision = detect_dj_readiness(self.analysis(8))
        self.assertEqual(decision.intro.mixable_bars, 8)
        self.assertGreater(decision.intro.confidence, 0.8)

    def test_stops_at_first_non_mixable_bar(self) -> None:
        decision = detect_dj_readiness(self.analysis(3))
        self.assertEqual(decision.intro.mixable_bars, 3)
        self.assertEqual(decision.outro.mixable_bars, 0)

    def test_never_counts_beyond_the_edge_analysis_window(self) -> None:
        decision = detect_dj_readiness(self.analysis(20, total=20))
        self.assertEqual(decision.intro.mixable_bars, 16)


if __name__ == "__main__":
    unittest.main()
