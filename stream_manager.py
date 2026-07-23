#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import time
import shutil

def check_dependencies():
    deps = ["ffmpeg", "Xvfb", "chromium-browser"]
    missing = []
    for dep in deps:
        if not shutil.which(dep):
            # Also check for 'chromium' or 'google-chrome'
            if dep == "chromium-browser" and (shutil.which("chromium") or shutil.which("google-chrome")):
                continue
            missing.append(dep)
    return missing

def get_chromium_executable():
    for cmd in ["chromium-browser", "chromium", "google-chrome"]:
        if shutil.which(cmd):
            return cmd
    return None

def run_fastapi_server(port=6020):
    print(f"[*] Starting FastAPI Server on port {port}...")
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", str(port), "--reload"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(3) # Wait for server to boot up
    return server_process

def start_linux_stream(match_key, stream_key, resolution, audio_source, port):
    missing_deps = check_dependencies()
    if missing_deps:
        print(f"[-] Missing system dependencies for headless Linux streaming: {', '.join(missing_deps)}")
        print("    Please run: sudo apt-get install -y xvfb chromium-browser ffmpeg")
        sys.exit(1)

    display = ":99"
    width, height = resolution.split("x")
    
    print("[*] Starting Xvfb Virtual Framebuffer on display :99...")
    xvfb_process = subprocess.Popen(
        ["Xvfb", display, "-screen", "0", f"{width}x{height}x24"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(2)
    
    os.environ["DISPLAY"] = display
    
    chromium_cmd = get_chromium_executable()
    overlay_url = f"http://localhost:{port}/overlay?match={match_key}"
    print(f"[*] Launching Chromium in virtual display on URL: {overlay_url}")
    chromium_process = subprocess.Popen(
        [
            chromium_cmd,
            "--no-sandbox",
            f"--window-size={width},{height}",
            "--window-position=0,0",
            "--kiosk",
            "--no-first-run",
            "--disable-infobars",
            overlay_url
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(3)
    
    print("[*] Building FFmpeg live stream pipeline...")
    # Base command capturing Xvfb
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "x11grab",
        "-video_size", f"{width}x{height}",
        "-framerate", "30",
        "-i", f"{display}.0"
    ]
    
    # Audio inputs
    if audio_source == "silent":
        ffmpeg_cmd += [
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"
        ]
    else:
        ffmpeg_cmd += [
            "-stream_loop", "-1",
            "-i", audio_source
        ]
        
    # Streaming parameters
    rtmp_url = f"rtmp://a.rtmp.youtube.com/live2/{stream_key}"
    ffmpeg_cmd += [
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-b:v", "2500k",
        "-maxrate", "2500k",
        "-bufsize", "5000k",
        "-pix_fmt", "yuv420p",
        "-g", "60", # Keyframe interval (2 seconds at 30fps)
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-f", "flv",
        rtmp_url
    ]
    
    print(f"[*] Starting FFmpeg encoder. Streaming to YouTube RTMP...")
    stream_process = subprocess.Popen(ffmpeg_cmd)
    
    try:
        while True:
            # Check if any process has died
            if xvfb_process.poll() is not None:
                raise RuntimeError("Xvfb terminated unexpectedly")
            if chromium_process.poll() is not None:
                raise RuntimeError("Chromium browser terminated unexpectedly")
            if stream_process.poll() is not None:
                raise RuntimeError("FFmpeg stream encoder terminated unexpectedly")
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n[*] Stopping stream gracefully...")
    finally:
        # Kill everything
        stream_process.terminate()
        chromium_process.terminate()
        xvfb_process.terminate()
        print("[*] Stream stopped.")

def start_macos_guide(match_key, port):
    print("=" * 70)
    print("                    MACOS STREAMING GUIDE (FREE)")
    print("=" * 70)
    print("OBS Studio is recommended on macOS because it supports hardware acceleration")
    print("and handles desktop display capture natively for free.\n")
    print("1. Download & Install OBS Studio: https://obsproject.com/")
    print("2. Open OBS Studio and create a new Scene.")
    print("3. Add a new 'Browser Source':")
    print(f"   - URL: http://localhost:{port}/overlay?match={match_key}")
    print("   - Width: 1920")
    print("   - Height: 1080")
    print("4. Add an Audio source if you want background music.")
    print("5. Go to OBS settings -> Stream -> Service: YouTube - RTMPS.")
    print("6. Enter your Stream Key and click 'Start Streaming'.\n")
    print(f"Open browser dashboard: http://localhost:{port}/")
    print(f"Open broadcast overlay: http://localhost:{port}/overlay?match={match_key}")
    print("=" * 70)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Shutting down...")

def main():
    parser = argparse.ArgumentParser(description="Automated YouTube Live Score Streaming Orchestrator")
    parser.add_argument("--match", default="127D", help="CREX Match key (e.g. 127D) or full Match URL")
    parser.add_argument("--stream-key", help="Your YouTube Live Stream Key (required on Linux for RTMP stream)")
    parser.add_argument("--resolution", default="1920x1080", help="Virtual screen resolution (default: 1920x1080)")
    parser.add_argument("--audio", default="silent", help="Audio source: 'silent' (default) or absolute path to an mp3 file")
    parser.add_argument("--port", type=int, default=6020, help="FastAPI port (default: 6020)")
    args = parser.parse_args()

    # Start FastAPI server
    server_process = run_fastapi_server(args.port)

    try:
        if sys.platform.startswith("linux"):
            if not args.stream_key:
                print("[-] Error: --stream-key is required on Linux to push RTMP stream to YouTube.")
                sys.exit(1)
            start_linux_stream(args.match, args.stream_key, args.resolution, args.audio, args.port)
        else:
            # macOS / Windows local guide
            start_macos_guide(args.match, args.port)
    finally:
        print("[*] Stopping FastAPI Server...")
        server_process.terminate()

if __name__ == "__main__":
    main()
