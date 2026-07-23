import html
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
)
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from crex_score import (
    NOT_FOUND,
    ScoreFetchError,
    extract_match_key,
    fetch_score_async,
    format_score_text,
)


class Team(BaseModel):
    code: str = NOT_FOUND
    name: str = NOT_FOUND
    short: Optional[str] = None
    color_dark: Optional[str] = None
    color_light: Optional[str] = None


class Batsman(BaseModel):
    name: str
    score: str
    fours: str
    sixes: str
    sr: str


class Bowler(BaseModel):
    name: Optional[str] = None
    score: Optional[str] = None
    overs: Optional[str] = None
    econ: Optional[str] = None


class ScoreResponse(BaseModel):
    status: str
    source: str
    match_key: str
    api_url: str
    teams: List[Team]
    batting_team: Team
    score: str
    innings_score: str
    opponent_score: str = "--"
    recent_over: List[str]
    current_batsmen: List[Batsman] = []
    current_bowler: Bowler = {}
    last_wicket: str = "--"
    partnership: str = "--"
    crr: str = "--"
    rrr: str = "--"
    win_probability: Dict[str, Any] = {}
    title: str = ""


app = FastAPI(
    title="CREX Score API",
    version="1.0.0",
    description="Live cricket score API backed by CREX score data",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)

    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, "
        "proxy-revalidate, max-age=0"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Surrogate-Control"] = "no-store"

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"

    if request.url.path in ["/overlay", "/"]:
        frame_policy = "*"
    else:
        response.headers["X-Frame-Options"] = "DENY"
        frame_policy = "'none'"

    response.headers["Content-Security-Policy"] = (
        "default-src 'self' http: https: data: 'unsafe-inline' 'unsafe-eval'; "
        "connect-src 'self' http: https: ws: wss:; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https:; "
        "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com; "
        "object-src 'none'; "
        f"frame-ancestors {frame_policy};"
    )

    return response


def render_dashboard(initial_match: str) -> str:
    safe_match = html.escape(initial_match, quote=True)

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>CREX Live Score Dashboard</title>
    <style>
        :root {{
            color-scheme: dark;
            --bg: #07111f;
            --panel: rgba(10, 20, 37, 0.86);
            --panel-strong: rgba(18, 33, 56, 0.95);
            --line: rgba(148, 163, 184, 0.18);
            --text: #e5eefc;
            --muted: #94a3b8;
            --accent: #60a5fa;
            --accent-2: #22c55e;
            --danger: #f87171;
            --shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
        }}

        * {{
            box-sizing: border-box;
        }}

        body {{
            margin: 0;
            min-height: 100vh;
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background:
                radial-gradient(circle at top left, rgba(96, 165, 250, 0.18), transparent 28%),
                radial-gradient(circle at top right, rgba(34, 197, 94, 0.15), transparent 22%),
                linear-gradient(180deg, #08111f 0%, #050b14 100%);
            color: var(--text);
        }}

        .shell {{
            width: min(1120px, calc(100% - 32px));
            margin: 0 auto;
            padding: 32px 0 48px;
        }}

        .hero {{
            display: grid;
            gap: 22px;
            margin-bottom: 24px;
        }}

        .hero-card {{
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 24px;
            padding: 24px;
            box-shadow: var(--shadow);
            backdrop-filter: blur(14px);
        }}

        .eyebrow {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 12px;
            border-radius: 999px;
            background: rgba(96, 165, 250, 0.12);
            color: #bfdbfe;
            font-size: 12px;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}

        h1 {{
            margin: 16px 0 10px;
            font-size: clamp(28px, 4vw, 44px);
            line-height: 1.04;
        }}

        .lead {{
            margin: 0;
            color: var(--muted);
            font-size: 16px;
            max-width: 760px;
            line-height: 1.6;
        }}

        .controls {{
            display: grid;
            grid-template-columns: minmax(0, 1fr) 160px 140px;
            gap: 12px;
            margin-top: 24px;
        }}

        .field,
        .select,
        .button {{
            width: 100%;
            min-height: 52px;
            border-radius: 16px;
            border: 1px solid var(--line);
            background: var(--panel-strong);
            color: var(--text);
            padding: 0 16px;
            font-size: 15px;
        }}

        .field:focus,
        .select:focus {{
            outline: 2px solid rgba(96, 165, 250, 0.5);
            border-color: rgba(96, 165, 250, 0.5);
        }}

        .button {{
            border: 0;
            cursor: pointer;
            background: linear-gradient(135deg, #2563eb 0%, #22c55e 100%);
            font-weight: 700;
        }}

        .meta {{
            margin-top: 14px;
            display: flex;
            flex-wrap: wrap;
            gap: 14px;
            color: var(--muted);
            font-size: 14px;
        }}

        .grid {{
            display: grid;
            grid-template-columns: repeat(12, minmax(0, 1fr));
            gap: 16px;
        }}

        .card {{
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 22px;
            padding: 20px;
            box-shadow: var(--shadow);
            backdrop-filter: blur(14px);
        }}

        .span-12 {{ grid-column: span 12; }}
        .span-8 {{ grid-column: span 8; }}
        .span-6 {{ grid-column: span 6; }}
        .span-4 {{ grid-column: span 4; }}

        .label {{
            color: var(--muted);
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 10px;
        }}

        .score {{
            font-size: clamp(34px, 5vw, 56px);
            font-weight: 800;
            line-height: 1.02;
            letter-spacing: -0.03em;
        }}

        .value {{
            font-size: 24px;
            font-weight: 700;
            line-height: 1.2;
        }}

        .subtle {{
            margin-top: 8px;
            color: var(--muted);
            font-size: 14px;
            line-height: 1.5;
        }}

        .pill-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}

        .pill {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 42px;
            min-height: 42px;
            padding: 0 14px;
            border-radius: 999px;
            background: rgba(96, 165, 250, 0.13);
            border: 1px solid rgba(96, 165, 250, 0.2);
            font-weight: 700;
        }}

        .teams {{
            display: grid;
            gap: 12px;
        }}

        .team {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            padding: 14px 16px;
            border-radius: 16px;
            background: rgba(148, 163, 184, 0.08);
            border: 1px solid rgba(148, 163, 184, 0.12);
        }}

        .team.active {{
            background: rgba(34, 197, 94, 0.12);
            border-color: rgba(34, 197, 94, 0.22);
        }}

        .status {{
            min-height: 24px;
            margin-top: 18px;
            font-size: 14px;
            color: var(--muted);
        }}

        .status.error {{
            color: var(--danger);
        }}

        .footer {{
            margin-top: 18px;
            color: var(--muted);
            font-size: 13px;
        }}

        @media (max-width: 900px) {{
            .controls {{
                grid-template-columns: 1fr;
            }}

            .span-8,
            .span-6,
            .span-4 {{
                grid-column: span 12;
            }}
        }}
    </style>
</head>
<body>
    <main class="shell">
        <section class="hero">
            <div class="hero-card">
                <div class="eyebrow">Live CREX Score Dashboard</div>
                <h1>Track live score, batting side, and recent over at a glance.</h1>
                <p class="lead">
                    Paste a CREX match URL or enter a match key like <code>127D</code>.
                    The dashboard polls your local API and refreshes automatically.
                </p>
                <div class="controls">
                    <input id="matchInput" class="field" type="text" value="{safe_match}" placeholder="Enter CREX match key or full match URL">
                    <select id="refreshSelect" class="select">
                        <option value="0">Manual refresh</option>
                        <option value="5">Refresh every 5s</option>
                        <option value="10" selected>Refresh every 10s</option>
                        <option value="15">Refresh every 15s</option>
                        <option value="30">Refresh every 30s</option>
                    </select>
                    <button id="loadButton" class="button" type="button">Load Score</button>
                </div>
                <div class="meta">
                    <span>API: <code>/api/score</code></span>
                    <span>Text Mode: <code>/api/score?match=127D&amp;text=true</code></span>
                    <span id="lastUpdated">Last updated: not yet loaded</span>
                </div>
                <div id="status" class="status">Ready</div>
            </div>
        </section>

        <section class="grid">
            <article class="card span-8">
                <div class="label">Current Score</div>
                <div id="scoreValue" class="score">Waiting for match...</div>
                <div id="inningsValue" class="subtle">Load a CREX match to see the latest score.</div>
            </article>

            <article class="card span-4">
                <div class="label">Batting Team</div>
                <div id="battingValue" class="value">-</div>
                <div id="matchKeyValue" class="subtle">Match key: -</div>
            </article>

            <article class="card span-6">
                <div class="label">Teams</div>
                <div id="teamsList" class="teams"></div>
            </article>

            <article class="card span-6">
                <div class="label">Recent Over</div>
                <div id="recentOverValue" class="pill-row"></div>
                <div class="footer">Ball-by-ball markers are shown from the latest over only.</div>
            </article>

            <article class="card span-12">
                <div class="label">API Endpoint</div>
                <div id="apiValue" class="subtle">-</div>
            </article>
        </section>
    </main>

    <script>
        const input = document.getElementById("matchInput");
        const refreshSelect = document.getElementById("refreshSelect");
        const loadButton = document.getElementById("loadButton");
        const statusEl = document.getElementById("status");
        const lastUpdatedEl = document.getElementById("lastUpdated");
        const scoreValueEl = document.getElementById("scoreValue");
        const inningsValueEl = document.getElementById("inningsValue");
        const battingValueEl = document.getElementById("battingValue");
        const matchKeyValueEl = document.getElementById("matchKeyValue");
        const teamsListEl = document.getElementById("teamsList");
        const recentOverValueEl = document.getElementById("recentOverValue");
        const apiValueEl = document.getElementById("apiValue");

        let refreshTimer = null;

        function setStatus(message, isError = false) {{
            statusEl.textContent = message;
            statusEl.classList.toggle("error", isError);
        }}

        function setLoadingState(isLoading) {{
            loadButton.disabled = isLoading;
            loadButton.textContent = isLoading ? "Loading..." : "Load Score";
        }}

        function renderTeams(data) {{
            teamsListEl.innerHTML = "";
            const battingCode = (data.batting_team && data.batting_team.code) || "";

            (data.teams || []).forEach((team) => {{
                const row = document.createElement("div");
                row.className = "team" + (team.code === battingCode ? " active" : "");
                row.innerHTML = `
                    <div>
                        <div class="value" style="font-size:18px;">${{team.name}}</div>
                        <div class="subtle" style="margin-top:4px;">Code: ${{team.code}}</div>
                    </div>
                    <div class="subtle">${{team.code === battingCode ? "Batting now" : "Waiting"}}</div>
                `;
                teamsListEl.appendChild(row);
            }});
        }}

        function renderRecentOver(data) {{
            recentOverValueEl.innerHTML = "";
            const balls = data.recent_over || [];

            if (!balls.length) {{
                const empty = document.createElement("div");
                empty.className = "subtle";
                empty.textContent = "No recent over data available yet.";
                recentOverValueEl.appendChild(empty);
                return;
            }}

            balls.forEach((ball) => {{
                const pill = document.createElement("div");
                pill.className = "pill";
                pill.textContent = ball;
                recentOverValueEl.appendChild(pill);
            }});
        }}

        function renderData(data) {{
            scoreValueEl.textContent = data.score || "-";
            inningsValueEl.textContent = "Innings score: " + (data.innings_score || "-");
            battingValueEl.textContent = (data.batting_team && data.batting_team.name) || "-";
            matchKeyValueEl.textContent = "Match key: " + (data.match_key || "-");
            apiValueEl.textContent = data.api_url || "-";

            renderTeams(data);
            renderRecentOver(data);

            const now = new Date().toLocaleTimeString();
            lastUpdatedEl.textContent = "Last updated: " + now;
        }}

        async function loadScore() {{
            const match = input.value.trim();

            if (!match) {{
                setStatus("Enter a CREX match key or URL first.", true);
                return;
            }}

            setLoadingState(true);
            setStatus("Fetching live score...");

            try {{
                const response = await fetch(`/api/score?match=${{encodeURIComponent(match)}}`);
                const data = await response.json();

                if (!response.ok || data.status !== "success") {{
                    throw new Error(data.message || "Unable to fetch score");
                }}

                renderData(data);
                setStatus("Live score updated.");

                const url = new URL(window.location.href);
                url.searchParams.set("match", match);
                window.history.replaceState({{}}, "", url);
            }} catch (error) {{
                setStatus(error.message, true);
            }} finally {{
                setLoadingState(false);
            }}
        }}

        function updateAutoRefresh() {{
            if (refreshTimer) {{
                window.clearInterval(refreshTimer);
                refreshTimer = null;
            }}

            const seconds = Number(refreshSelect.value);
            if (seconds > 0) {{
                refreshTimer = window.setInterval(loadScore, seconds * 1000);
            }}
        }}

        loadButton.addEventListener("click", loadScore);
        input.addEventListener("keydown", (event) => {{
            if (event.key === "Enter") {{
                loadScore();
            }}
        }});
        refreshSelect.addEventListener("change", updateAutoRefresh);

        updateAutoRefresh();

        if (input.value.trim()) {{
            loadScore();
        }}
    </script>
</body>
</html>
"""


async def load_score(match: str) -> ScoreResponse:
    try:
        extract_match_key(match)
    except ValueError as exc:
        raise ScoreFetchError(422, str(exc)) from exc

    return ScoreResponse(**await fetch_score_async(match))


@app.get("/health", tags=["System"], summary="Health Check")
async def health_check():
    """Health check endpoint to verify API service status."""
    return {"status": "ok", "service": "live-cricket-score-api", "version": "1.0.0"}


@app.get("/", response_class=HTMLResponse, tags=["Dashboard"], summary="Live Cricket Web Dashboard")
async def root(
    match: Optional[str] = Query(
        "127D",
        description="CREX match URL or match key (e.g. 127D or 12UZ)",
    ),
):
    """Renders the standalone live cricket web dashboard interface."""
    return HTMLResponse(render_dashboard(match or "127D"))


@app.get("/overlay", response_class=HTMLResponse, tags=["Broadcast Overlay"], summary="OBS Live Stream Overlay")
async def overlay(
    match: Optional[str] = Query(
        "127D",
        description="CREX match URL or match key (e.g. 127D or 12UZ)",
    ),
    watermark: Optional[str] = Query(
        None,
        description="Custom producer watermark name for broadcast graphic badge",
    ),
):
    """Renders the 1080p transparent OBS Studio broadcast graphics overlay."""
    try:
        import os
        if os.path.exists("index.html"):
            with open("index.html", "r", encoding="utf-8") as f:
                content = f.read()
            if match:
                content = content.replace("const DEFAULT_MATCH_ID = '127D';", f"const DEFAULT_MATCH_ID = '{match}';")
                content = content.replace('const DEFAULT_MATCH_ID = "127D";', f"const DEFAULT_MATCH_ID = '{match}';")
            return HTMLResponse(content)
        else:
            return HTMLResponse("index.html not found", status_code=404)
    except Exception as e:
        return HTMLResponse(f"Error loading overlay: {e}", status_code=500)


@app.get(
    "/api/score",
    response_model=ScoreResponse,
    tags=["Live Score Data"],
    summary="Get Real-Time Live Cricket Score Payload",
)
async def api_score(
    match: str = Query(
        ...,
        description="CREX match key or full CREX match URL (e.g. 12UZ)",
    ),
    text: bool = Query(
        False,
        description="Set to true for plain-text tree output instead of JSON",
    ),
):
    """Fetches real-time score payload, bowler stats, batsman scores, win probabilities, and recent overs."""
    result = await load_score(match)

    if text:
        return PlainTextResponse(format_score_text(result.model_dump()))

    return result


@app.exception_handler(ScoreFetchError)
async def api_error_handler(request: Request, exc: ScoreFetchError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "code": exc.status_code,
            "message": exc.message,
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    request: Request,
    exc: StarletteHTTPException
):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "code": exc.status_code,
            "message": "invalid api route",
        },
    )


@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "code": 500,
            "message": "internal server error",
        },
    )
