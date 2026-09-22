#!/usr/bin/env python3
"""
DeepShield Mobile — Latency & Throughput Benchmark Suite
Tests edge processing speed across:
1. Zero-Copy YUV Luminance Plane Analysis (CameraX simulation)
2. 1024-point FFT & 1.2 kHz - 3.5 kHz Acoustic Resonance Analysis (Oboe simulation)
3. OriginOS Office Kit Cryptogram Generation (HMAC-SHA256 & AES-GCM)
4. End-to-End Pipeline Latency Validation (<10ms target)
"""

import time
import math
import cmath
import os
import hmac
import hashlib
import statistics
import unittest

def bit_reverse_indices(n):
    bits = int(math.log2(n))
    rev = [0] * n
    for i in range(n):
        r = 0
        for j in range(bits):
            if (i >> j) & 1:
                r |= (1 << (bits - 1 - j))
        rev[i] = r
    return rev

# Precomputed bit-reversal table for 1024 FFT
REV_TABLE_1024 = bit_reverse_indices(1024)

def radix2_fft(data):
    n = len(data)
    # Bit reversal
    out = [data[REV_TABLE_1024[i]] for i in range(n)]

    length = 2
    while length <= n:
        half = length // 2
        angle = -2.0 * math.pi / length
        w_len = complex(math.cos(angle), math.sin(angle))
        for i in range(0, n, length):
            w = complex(1.0, 0.0)
            for j in range(half):
                u = out[i + j]
                v = out[i + j + half] * w
                out[i + j] = u + v
                out[i + j + half] = u - v
                w *= w_len
        length <<= 1
    return out

def simulate_visual_yuv_scan(y_buffer_bytes, width=640, height=480):
    """Simulates CameraX direct ByteBuffer scan on 640x480 Y luminance channel."""
    roi_start_x = width // 6
    roi_end_x = (width * 5) // 6
    roi_start_y = height // 4
    roi_end_y = (height * 3) // 4
    step_y = 4
    step_x = 2

    edge_spans = []
    gradient_sum = 0
    high_freq_moire = 0
    count = 0

    for y in range(roi_start_y, roi_end_y, step_y):
        row_offset = y * width
        last_edge_x = -1
        prev_lum = 0

        for x in range(roi_start_x, roi_end_x, step_x):
            idx = row_offset + x
            lum = y_buffer_bytes[idx]
            if x > roi_start_x:
                grad = abs(lum - prev_lum)
                gradient_sum += grad
                count += 1
                if grad > 48:
                    if last_edge_x != -1:
                        span = x - last_edge_x
                        if 3 <= span <= 40:
                            edge_spans.append(span)
                    last_edge_x = x
                if grad > 70:
                    high_freq_moire += 1
            prev_lum = lum

    kerning_var = 0.0
    if len(edge_spans) > 10:
        mean = sum(edge_spans) / len(edge_spans)
        var = sum((s - mean) ** 2 for s in edge_spans) / len(edge_spans)
        kerning_var = math.sqrt(var)

    moire_idx = (high_freq_moire / count * 100.0) if count > 0 else 0.0
    anomaly_score = min(1.0, max(0.0, ((kerning_var - 3.0) / 6.0) * 0.65 + (moire_idx / 15.0) * 0.35))
    return kerning_var, moire_idx, anomaly_score

def simulate_acoustic_fft(pcm_samples, sample_rate=16000):
    """Simulates 1024-point FFT & 1.2kHz - 3.5kHz resonance chamber band energy extraction."""
    # Apply Hann window
    n = len(pcm_samples)
    windowed = [pcm_samples[i] * 0.5 * (1.0 - math.cos(2.0 * math.pi * i / (n - 1))) for i in range(n)]
    fft_res = radix2_fft([complex(x, 0.0) for x in windowed])

    bin_min = int((1200.0 * n) / sample_rate)
    bin_max = int((3500.0 * n) / sample_rate)

    total_energy = 1e-7
    resonance_energy = 0.0

    for k in range(1, n // 2):
        mag = abs(fft_res[k])
        power = mag * mag
        total_energy += power
        if bin_min <= k <= bin_max:
            resonance_energy += power

    ratio = resonance_energy / total_energy
    return ratio

def simulate_office_kit_cryptogram(visual_score, acoustic_ratio):
    secret = b"iQOO_ORIGIN_OS_OFFICE_KIT_SECRET"
    payload = f'{{"session":"IQOO-BENCHMARK","v":{visual_score:.3f},"a":{acoustic_ratio:.3f},"time":{int(time.time()*1000)}}}'
    digest = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    return digest


class BenchmarkTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Generate synthetic 640x480 YUV frame
        cls.synthetic_frame = bytearray(os.urandom(640 * 480))
        # Generate synthetic 1024 16kHz PCM audio samples (with 2kHz resonant peak)
        cls.synthetic_pcm = [
            0.6 * math.sin(2.0 * math.pi * 2200.0 * i / 16000.0) +
            0.1 * math.sin(2.0 * math.pi * 500.0 * i / 16000.0)
            for i in range(1024)
        ]

    def test_visual_yuv_scan_latency(self):
        iterations = 200
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            simulate_visual_yuv_scan(self.synthetic_frame)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0)

        p50 = statistics.median(latencies)
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        print(f"\n[BENCHMARK] CameraX Y-Plane Zero-Copy Scan (200 runs): P50={p50:.3f}ms, P95={p95:.3f}ms")
        self.assertLess(p50, 4.5, "Visual frame scan median must be under 4.5ms")

    def test_acoustic_fft_latency(self):
        iterations = 200
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            ratio = simulate_acoustic_fft(self.synthetic_pcm)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0)

        p50 = statistics.median(latencies)
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        print(f"[BENCHMARK] 1024-Point FFT & Resonance DSP (200 runs): P50={p50:.3f}ms, P95={p95:.3f}ms")
        self.assertGreater(ratio, 0.45, "Resonant 2.2kHz signal should yield strong chamber ratio (>45%)")
        self.assertLess(p50, 3.5, "Acoustic FFT median must be under 3.5ms")

    def test_cryptogram_latency(self):
        iterations = 500
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            simulate_office_kit_cryptogram(0.05, 0.68)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0)

        p50 = statistics.median(latencies)
        print(f"[BENCHMARK] OriginOS Office Kit Cryptogram (500 runs): P50={p50:.4f}ms")
        self.assertLess(p50, 0.2, "Cryptogram generation must be under 0.2ms")

    def test_end_to_end_sub_10ms_target(self):
        iterations = 100
        total_latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            _, _, v_score = simulate_visual_yuv_scan(self.synthetic_frame)
            a_ratio = simulate_acoustic_fft(self.synthetic_pcm)
            simulate_office_kit_cryptogram(v_score, a_ratio)
            t1 = time.perf_counter()
            total_latencies.append((t1 - t0) * 1000.0)

        p50 = statistics.median(total_latencies)
        p99 = sorted(total_latencies)[int(len(total_latencies) * 0.99)]
        print(f"[BENCHMARK] End-to-End Dual-Modal Edge Gate: P50={p50:.3f}ms, P99={p99:.3f}ms")
        self.assertLess(p50, 8.0, "Dual-Modal median end-to-end latency must satisfy <8ms (<10ms target)")
        print(f"  >>> SUB-10MS LATENCY TARGET MET (P50: {p50:.2f}ms | Target: <10.0ms) <<<\n")


if __name__ == "__main__":
    unittest.main()
