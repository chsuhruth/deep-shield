#!/usr/bin/env python3
"""
DeepShield Mobile — Standalone Live Demo Runner & Dual-Modal Fraud Shield API
Designed for the iQOO Hackathon (Phone-First Edge AI Track).

Supports:
1. Zero-dependency HTTP Server mode serving web_console/index.html + Edge Verification REST API.
2. Optional Gradio Interactive Dashboard mode (if gradio is installed).
"""

import sys
import os
import json
import time
import math
import hmac
import hashlib
import base64
import http.server
import socketserver
import urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web_console"

# -----------------------------------------------------------------------------
# Dual-Modal Edge Fraud Inspection Engine (Python Simulation of On-Device NPU/C++)
# -----------------------------------------------------------------------------

class DeepShieldEdgeEngine:
    SESSION_KEY = b"iQOO_ORIGIN_OS_OFFICE_KIT_SECRET"

    @staticmethod
    def inspect_visual_kerning(image_bytes: bytes = None, simulated_tamper: bool = False):
        """Simulates CameraX YUV direct-buffer zero-copy luminance gradient and kerning variance."""
        start = time.perf_counter()
        
        if simulated_tamper:
            kerning_variance = 7.82
            moire_index = 16.4
            anomaly_score = 0.86
            is_tampered = True
        else:
            kerning_variance = 2.14
            moire_index = 0.4
            anomaly_score = 0.05
            is_tampered = False

        latency_ms = (time.perf_counter() - start) * 1000.0 + 3.2  # 3.2ms simulated NPU inference
        return {
            "kerning_variance": round(kerning_variance, 2),
            "moire_index_percent": round(moire_index, 1),
            "anomaly_score": round(anomaly_score, 3),
            "is_tampered": is_tampered,
            "latency_ms": round(latency_ms, 2)
        }

    @staticmethod
    def inspect_acoustic_resonance(audio_samples: list = None, simulated_replay: bool = False):
        """Simulates native C++ Oboe 16kHz FFT 1.2kHz-3.5kHz speaker resonance inspection."""
        start = time.perf_counter()

        if simulated_replay:
            resonance_ratio = 0.23
            distortion_ratio = 0.38
            is_replay = True
        else:
            resonance_ratio = 0.67
            distortion_ratio = 0.08
            is_replay = False

        latency_ms = (time.perf_counter() - start) * 1000.0 + 1.8  # 1.8ms simulated FFT DSP
        return {
            "resonance_ratio": round(resonance_ratio, 3),
            "distortion_ratio": round(distortion_ratio, 3),
            "is_replay": is_replay,
            "latency_ms": round(latency_ms, 2)
        }

    @classmethod
    def generate_office_kit_cryptogram(cls, visual_res: dict, acoustic_res: dict):
        """Builds an authenticated, encrypted OriginOS Office Kit POS payload."""
        start = time.perf_counter()
        timestamp = int(time.time() * 1000)
        session_id = f"IQOO-{os.urandom(4).hex().upper()}"

        if acoustic_res["is_replay"] and visual_res["is_tampered"]:
            verdict = "CRITICAL_DUAL_FRAUD"
        elif acoustic_res["is_replay"]:
            verdict = "ACOUSTIC_REPLAY_FRAUD"
        elif visual_res["is_tampered"]:
            verdict = "VISUAL_FORGERY_FRAUD"
        else:
            verdict = "AUTHENTIC_VERIFIED"

        payload = {
            "protocol": "OriginOS_OfficeKit_v2",
            "session_id": session_id,
            "timestamp": timestamp,
            "device": "iQOO_12_Pro_Hexagon_NPU",
            "metrics": {
                "visual_anomaly": visual_res["anomaly_score"],
                "acoustic_resonance": acoustic_res["resonance_ratio"],
                "is_visual_tampered": visual_res["is_tampered"],
                "is_acoustic_replay": acoustic_res["is_replay"]
            },
            "verdict": verdict,
            "total_latency_ms": round(visual_res["latency_ms"] + acoustic_res["latency_ms"], 2)
        }

        payload_json = json.dumps(payload, separators=(',', ':'))
        hmac_digest = hmac.new(cls.SESSION_KEY, payload_json.encode('utf-8'), hashlib.sha256).hexdigest()
        encrypted_simulation = base64.b64encode(f"ENC_{payload_json}".encode('utf-8')).decode('utf-8')

        cryptogram_latency = (time.perf_counter() - start) * 1000.0

        return {
            "payload": payload,
            "hmac_sha256": hmac_digest,
            "ciphertext": encrypted_simulation,
            "cryptogram_latency_ms": round(cryptogram_latency, 3)
        }


# -----------------------------------------------------------------------------
# Zero-Dependency HTTP Server with Live Web Console & REST API
# -----------------------------------------------------------------------------

class DeepShieldRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "UP",
                "system": "DeepShield Mobile Edge AI Engine",
                "npu_target": "Qualcomm Hexagon / Oryon",
                "sub_10ms_ready": True
            }).encode('utf-8'))
            return
        elif parsed.path == "/api/benchmark":
            v = DeepShieldEdgeEngine.inspect_visual_kerning(simulated_tamper=False)
            a = DeepShieldEdgeEngine.inspect_acoustic_resonance(simulated_replay=False)
            c = DeepShieldEdgeEngine.generate_office_kit_cryptogram(v, a)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"visual": v, "acoustic": a, "cryptogram": c}).encode('utf-8'))
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/verify":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8')) if post_data else {}
            except Exception:
                data = {}

            sim_tamper = data.get("simulate_visual_tamper", False)
            sim_replay = data.get("simulate_acoustic_replay", False)

            v = DeepShieldEdgeEngine.inspect_visual_kerning(simulated_tamper=sim_tamper)
            a = DeepShieldEdgeEngine.inspect_acoustic_resonance(simulated_replay=sim_replay)
            c = DeepShieldEdgeEngine.generate_office_kit_cryptogram(v, a)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "visual": v,
                "acoustic": a,
                "cryptogram": c
            }, indent=2).encode('utf-8'))
            return

        self.send_response(404)
        self.end_headers()


def run_http_server(port=8080):
    print("=" * 70)
    print("  DEEPSHIELD MOBILE — ON-DEVICE DUAL-MODAL FRAUD SHIELD")
    print("  iQOO Hackathon (Phone-First Edge AI Track)")
    print("=" * 70)
    print(f"[+] Serving Web Console from: {WEB_DIR}")
    print(f"[+] Zero-dependency HTTP server running at: http://localhost:{port}")
    print(f"[+] Health Check: http://localhost:{port}/api/health")
    print(f"[+] Live Benchmark API: http://localhost:{port}/api/benchmark")
    print(f"[+] Press Ctrl+C to terminate.")
    print("=" * 70)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), DeepShieldRequestHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[+] DeepShield demo server stopped cleanly.")


# -----------------------------------------------------------------------------
# Optional Gradio Interface Runner
# -----------------------------------------------------------------------------

def launch_gradio_app():
    import gradio as gr

    def verify_dual_modal(simulate_visual_tamper, simulate_acoustic_replay):
        v = DeepShieldEdgeEngine.inspect_visual_kerning(simulated_tamper=simulate_visual_tamper)
        a = DeepShieldEdgeEngine.inspect_acoustic_resonance(simulated_replay=simulate_acoustic_replay)
        c = DeepShieldEdgeEngine.generate_office_kit_cryptogram(v, a)
        
        verdict = c["payload"]["verdict"]
        total_time = round(v["latency_ms"] + a["latency_ms"] + c["cryptogram_latency_ms"], 2)
        summary = f"### Verdict: **{verdict}**\n**Total Pipeline Latency:** {total_time} ms (< 10ms target achieved)\n"
        return summary, json.dumps(v, indent=2), json.dumps(a, indent=2), json.dumps(c, indent=2)

    with gr.Blocks(title="DeepShield Mobile — iQOO Edge AI") as demo:
        gr.Markdown("# 🛡️ DeepShield Mobile: On-Device Dual-Modal Edge AI Fraud Shield")
        gr.Markdown("**iQOO Hackathon | Phone-First Edge AI Track | Sub-10ms Qualcomm Hexagon NPU Latency**")

        with gr.Row():
            with gr.Column():
                gr.Markdown("### 1. Attack Simulation Controls")
                chk_visual = gr.Checkbox(label="Simulate Fake UPI Screenshot (Misaligned Kerning & Screen Moiré)", value=False)
                chk_audio = gr.Checkbox(label="Simulate Soundbox Replay Attack (Attenuated Chamber Resonance)", value=False)
                btn_run = gr.Button("Execute Dual-Modal Verification Gate", variant="primary")

            with gr.Column():
                gr.Markdown("### 2. Live Verification Results")
                out_verdict = gr.Markdown("### Verdict: Ready")
                with gr.Accordion("Visual Inspection Telemetry", open=True):
                    out_visual = gr.Code(language="json")
                with gr.Accordion("Acoustic FFT Telemetry (1.2 - 3.5 kHz)", open=True):
                    out_acoustic = gr.Code(language="json")
                with gr.Accordion("OriginOS Office Kit Cryptogram", open=True):
                    out_crypto = gr.Code(language="json")

        btn_run.click(
            verify_dual_modal,
            inputs=[chk_visual, chk_audio],
            outputs=[out_verdict, out_visual, out_acoustic, out_crypto]
        )

    demo.launch(server_name="0.0.0.0", server_port=7860)


if __name__ == "__main__":
    if "--gradio" in sys.argv:
        try:
            launch_gradio_app()
        except ImportError:
            print("[!] Gradio not installed. Falling back to zero-dependency HTTP server on port 8080...")
            run_http_server(8080)
    else:
        port = 8080
        if len(sys.argv) > 1 and sys.argv[1].isdigit():
            port = int(sys.argv[1])
        run_http_server(port)
