# 🏏 Live Cricket Score API & Broadcast Graphics Package

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Author](https://img.shields.io/badge/Author-Chiluveru%20S%20Nohith-orange.svg)](https://github.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OBS Ready](https://img.shields.io/badge/OBS-Browser%20Source%20Ready-purple.svg)](https://obsproject.com/)

A high-performance **FastAPI backend** and **OBS Broadcast Graphics Overlay** package designed for live cricket streaming and score tracking. Created by **Chiluveru S Nohith**. Powered by CREX real-time socket streams, it delivers live ball-by-ball score data, dynamic player profiles, win probability gauge meters, customizable broadcast overlays, and on-screen producer watermarks.

---

## ✨ Features

- **⚡ Fast Async API**: Built with FastAPI & HTTPX for low-latency live score retrieval.
- **🎨 OBS Broadcast Overlay**: Transparent, 1080p responsive glassmorphic overlay with dynamic producer watermarking.
- **🏷️ Customizable Watermark**: Features built-in producer watermark (`PRODUCER: CHILUVERU S NOHITH`), customizable via URL query parameter (`?watermark=Your+Name`).
- **📊 Win Probability Gauge**: Real-time interactive SVG arc gauge dial tracking match win probabilities.
- **🎛️ Hotkey Control Engine**: Live layout state toggling directly in the browser (`0` Auto, `1` Score Bug, `2` Player Cards, `3` Full Dashboard).
- **🔄 Smart Player Resolver**: Self-healing player mapping parser with automatic cache-bypass triggers for new batsmen & bowlers.
- **📺 Event Animations**: Dynamic alert overlays for **6s**, **4s**, and **Wickets**.
- **📜 CLI & Text Endpoint**: Command-line interface and plain text formatting for lightweight displays or bot integrations.

---

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/live-cricket-score-api.git
cd live-cricket-score-api
```

### 2. Setup Virtual Environment & Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run Server (Single Command)
```bash
cd /path/to/live-cricket-score-api && ./venv/bin/uvicorn app:app --host 0.0.0.0 --port 6021 --reload
```

---

## 🎥 OBS Studio Integration Guide

1. Open **OBS Studio** and add a new **Browser Source** in your Scene.
2. Set the URL to:
   ```text
   http://localhost:6021/overlay?match=YOUR_MATCH_KEY
   ```
   *(Example: `http://localhost:6021/overlay?match=12UZ` or full CREX match URL)*
3. Set width and height:
   - **Width**: `1920`
   - **Height**: `1080`
4. Check **"Shutdown source when not visible"** (optional).
5. The overlay features a 100% transparent background, allowing your live stream video to show through seamlessly behind the graphics!

### ⌨️ Browser Interactive Hotkeys

When testing or controlling the overlay in Chrome:
- **`3`** — Lock **Full Scoreboard Dashboard** (Scoreboard + Win Probability + Player Cards + Ticker)
- **`2`** — Lock **Player Cards Panel** (Player profiles + Score Bug)
- **`1`** — Lock **HUD Score Bug** (Compact bottom-left score strip)
- **`0`** — Enable **Auto Broadcast Mode** (Transitions dynamically between states)

---

## 🔌 API Reference

### 1. Fetch Live Score (JSON)
`GET /api/score?match={MATCH_KEY_OR_URL}`

```json
{
  "status": "success",
  "source": "crex",
  "match_key": "12UZ",
  "teams": [
    { "code": "YAR", "name": "Genid Yanam Royals" },
    { "code": "KAK", "name": "Karaikal Kniights" }
  ],
  "score": "Karaikal Kniights 62/1 (7.0)",
  "recent_over": ["4", "1", "1", "1", "1"],
  "current_batsmen": [
    { "name": "Gautam Shastry", "score": "18 (12)", "fours": "3", "sixes": "0", "sr": "150.00" },
    { "name": "Mohammed Aqib Jawad", "score": "9 (12)*", "fours": "0", "sixes": "0", "sr": "75.00" }
  ],
  "current_bowler": {
    "name": "Pradeep Jakhar",
    "score": "0-8 (0.5)",
    "overs": "0.5",
    "econ": "9.60"
  },
  "win_probability": {
    "team1": 15.0,
    "team2": 85.0
  }
}
```

### 2. Plain Text Output
`GET /api/score?match={MATCH_KEY_OR_URL}&text=true`

### 3. Interactive Web Dashboard
`GET /?match={MATCH_KEY_OR_URL}`

---

## 💻 CLI Usage

```bash
# Get formatted text score
python cli.py 12UZ

# Output raw JSON score
python cli.py 12UZ --json

# Pass full match URL
python cli.py "https://crex.com/cricket-live-score/match-updates-12UZ"
```

---

## 🧪 Testing

Run the automated Pytest suite locally:

```bash
pytest tests/
```

The test suite covers:
- `/health` endpoint status
- `/api/score` JSON & text payload formats
- `/overlay` transparent framing security headers
- Invalid match key validation error handling (422)
- 404 route handling

---

## ❓ FAQ & Troubleshooting

### Q: Why does the overlay show `--/--`?
**A**: Ensure your match key is valid (e.g. `12UZ` or `127D`). If the match has not started yet or has finished, CREX socket payloads may be empty.

### Q: How do I change the broadcast watermark?
**A**: Pass `&watermark=Your+Channel+Name` in the OBS Browser Source URL:
`http://localhost:6021/overlay?match=12UZ&watermark=Stream+Cricket+Live`

### Q: Will OBS block the overlay framing?
**A**: No. Security headers on `/overlay` permit `frame-ancestors *` specifically for OBS Studio, vMix, and streaming software.

---

## 🛠️ Project Architecture

```text
├── app.py                  # FastAPI application & route controllers
├── crex_score.py           # Core score parser, socket decoder & player mapping engine
├── cli.py                  # Command-line interface tool
├── stream_manager.py       # Live stream state manager
├── index.html              # Broadcast graphics overlay frontend (Tailwind CSS v4 & JS)
├── index_broadcast.html    # Standalone broadcast overlay reference template
├── tests/                  # Pytest automated test suite
├── .github/                # GitHub Actions CI workflow & issue templates
├── requirements.txt        # Python package dependencies
├── LICENSE                 # MIT Open Source License
└── README.md               # Project documentation
```

---

## 🤝 Contributing

Contributions are welcome! If you'd like to improve the project:
1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for full details.

---

## ⚠️ Disclaimer

This project is intended for educational, learning, and personal broadcast use. It is **not affiliated with or endorsed by CREX**. Users are responsible for ensuring their usage complies with relevant terms of service.

---

## 📄 License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for details.
