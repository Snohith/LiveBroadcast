import asyncio
import json
import re
from typing import Any, Dict, List
import unicodedata
from urllib.parse import urlparse

import httpx


NOT_FOUND = "score not found"
REQUEST_TIMEOUT = "request timeout"

API_URL = "https://api.goscorer.com/api/v3/getSV3?key={match_key}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/146.0.0.0 "
        "Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://crex.com/",
    "Origin": "https://crex.com",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

MAP_CACHE = {}


class ScoreFetchError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def extract_match_key(match_value: str) -> str:
    value = (match_value or "").strip()

    if not value:
        raise ValueError("match value cannot be empty")

    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        tail = parsed.path.rstrip("/").split("/")[-1]
        if not tail:
            raise ValueError("unable to extract match key from url")
        value = tail.split("-")[-1]

    value = value.strip().upper()

    if not re.fullmatch(r"[A-Z0-9]{3,20}", value):
        raise ValueError("match must be a CREX url or key")

    return value


def build_api_url(match_key: str) -> str:
    return API_URL.format(match_key=match_key)


def normalize_score(raw_score: Any) -> str:
    text = str(raw_score or "").strip()

    if not text:
        return NOT_FOUND

    text = re.sub(r"(\d+/\d+)\(", r"\1 (", text)

    if "(" in text and ")" not in text:
        text = f"{text})"

    return text


def clean_team_code(team_code: Any) -> str:
    return str(team_code or "").replace("^", "").strip().upper()


def parse_teams(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    speech_names = payload.get("speech_names") or {}
    codes = [
        code.strip().upper()
        for code in str(payload.get("a") or "").split(".")
        if code.strip()
    ]

    teams = []
    for code in codes:
        teams.append(
            {
                "code": code,
                "name": speech_names.get(code, code),
            }
        )

    return teams


def parse_recent_over(payload: Dict[str, Any]) -> List[str]:
    recent_balls = payload.get("rb") or []

    if not recent_balls:
        return []

    latest_over = recent_balls[-1]
    if not isinstance(latest_over, dict):
        return []
        
    balls = latest_over.get("b") or []

    return [str(ball.get("u", "")).strip() for ball in balls if str(ball.get("u", "")).strip()]


def _extract_mapping_block(html: str) -> dict:
    """Extract the nested JSON block after getHomeMapDataliveparsing&q;: using brace-depth counting."""
    marker = "getHomeMapDataliveparsing&q;:"
    idx = html.find(marker)
    if idx < 0:
        return {}
    start = html.find("{", idx + len(marker))
    if start < 0:
        return {}
    depth = 0
    end = start
    for i in range(start, len(html)):
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    block = html[start:end + 1].replace("&q;", '"')
    try:
        return json.loads(block)
    except Exception:
        return {}


def _parse_mapping_data(data: dict) -> tuple[dict, dict, str]:
    """Extract player_map, team_map, series_name from parsed mapping JSON."""
    player_map = {}
    team_map = {}
    series_name = ""

    for p in data.get("p", []):
        if "f_key" in p and "n" in p:
            player_map[p["f_key"]] = p["n"]

    for t in data.get("t", []):
        if "f_key" in t:
            team_map[t["f_key"]] = {
                "name": t.get("n", ""),
                "short": t.get("sn", ""),
                "color_dark": t.get("dc", ""),
                "color_light": t.get("uc", "")
            }

    for s in data.get("s", []):
        if "n" in s:
            series_name = s["n"]
            break

    return player_map, team_map, series_name


def _resolve_match_url(match_key: str, home_html: str) -> str:
    pattern = rf'href="([^"]*?-{match_key}[^"]*?)"'
    matches = re.findall(pattern, home_html)
    if matches:
        return f"https://crex.com{matches[0]}"
    return f"https://crex.com/cricket-live-score/match-updates-{match_key}"


def get_match_mappings_sync(match_key: str, force: bool = False) -> tuple[dict, dict, str]:
    global MAP_CACHE
    if not force and match_key in MAP_CACHE:
        cached_p, cached_t, cached_s = MAP_CACHE[match_key]
        if cached_p: # Only use cache if it actually contains mappings!
            return cached_p, cached_t, cached_s

    player_map = {}
    team_map = {}
    series_name = ""

    try:
        headers = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://crex.com/", "Origin": "https://crex.com"}
        with httpx.Client(timeout=8.0, follow_redirects=True) as client:
            # Try direct match URL first
            match_url = f"https://crex.com/cricket-live-score/match-updates-{match_key}"
            page_res = client.get(match_url, headers=headers)
            html = page_res.text

            # If not found on direct url, try via homepage link scraping
            if "getHomeMapDataliveparsing" not in html:
                home_res = client.get("https://crex.com/", headers=headers)
                match_url = _resolve_match_url(match_key, home_res.text)
                page_res = client.get(match_url, headers=headers)
                html = page_res.text

            data = _extract_mapping_block(html)
            if data:
                player_map, team_map, series_name = _parse_mapping_data(data)
    except Exception:
        pass

    if player_map: # Only save to cache if successful
        MAP_CACHE[match_key] = (player_map, team_map, series_name)
    return player_map, team_map, series_name


async def get_match_mappings_async(match_key: str, force: bool = False) -> tuple[dict, dict, str]:
    global MAP_CACHE
    if not force and match_key in MAP_CACHE:
        cached_p, cached_t, cached_s = MAP_CACHE[match_key]
        if cached_p: # Only use cache if it actually contains mappings!
            return cached_p, cached_t, cached_s

    player_map = {}
    team_map = {}
    series_name = ""

    try:
        headers = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://crex.com/", "Origin": "https://crex.com"}
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            # Try direct match URL first
            match_url = f"https://crex.com/cricket-live-score/match-updates-{match_key}"
            page_res = await client.get(match_url, headers=headers)
            html = page_res.text

            # If not found on direct url, try via homepage link scraping
            if "getHomeMapDataliveparsing" not in html:
                home_res = await client.get("https://crex.com/", headers=headers)
                match_url = _resolve_match_url(match_key, home_res.text)
                page_res = await client.get(match_url, headers=headers)
                html = page_res.text

            data = _extract_mapping_block(html)
            if data:
                player_map, team_map, series_name = _parse_mapping_data(data)
    except Exception:
        pass

    if player_map: # Only save to cache if successful
        MAP_CACHE[match_key] = (player_map, team_map, series_name)
    return player_map, team_map, series_name


def normalize_player_name(name: str) -> str:
    # Normalize unicode to decompose accents (NFKD form) and ignore non-ASCII characters
    ascii_name = unicodedata.normalize('NFKD', str(name or "")).encode('ASCII', 'ignore').decode('utf-8')
    clean = ascii_name.lower()
    clean = re.sub(r"\((c|w|c\s*&\s*wk|wk|wk\s*&\s*c)\)", "", clean)
    clean = re.sub(r"[^a-z0-9]", "", clean)
    return clean.strip()


def get_live_scorecard_details_sync(match_key: str) -> tuple[dict, dict]:
    """Fetch and parse live scorecard details from Crex html page."""
    batsmen = {}
    bowlers = {}
    try:
        headers = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://crex.com/", "Origin": "https://crex.com"}
        url = f"https://crex.com/cricket-live-score/match-scorecard-{match_key}"
        with httpx.Client(timeout=6.0, follow_redirects=True) as client:
            res = client.get(url, headers=headers)
            if res.status_code == 200:
                html = res.text
                # Batsmen
                bat_pattern = r'<div[^>]*?class="batsman-name".*?<a[^>]*?title="([^"]+)".*?run-highlight">(\d+)</div>.*?class="">(\d+)</div>.*?class="">(\d+)</div>.*?class="">(\d+)</div>.*?class="">([\d.]+)</div>'
                for m in re.finditer(bat_pattern, html, re.DOTALL):
                    name = m.group(1).strip()
                    batsmen[normalize_player_name(name)] = {
                        "runs": m.group(2),
                        "balls": m.group(3),
                        "fours": m.group(4),
                        "sixes": m.group(5),
                        "sr": m.group(6)
                    }
                # Bowlers
                bowl_pattern = r'<div[^>]*?class="bowler-name".*?<a[^>]*?title="([^"]+)".*?run-highlight">([\d.]+)</div>.*?class="">(\d+)</div>.*?class="">(\d+)</div>.*?class="">(\d+)</div>.*?class="">([\d.]+)</div>'
                for m in re.finditer(bowl_pattern, html, re.DOTALL):
                    name = m.group(1).strip()
                    bowlers[normalize_player_name(name)] = {
                        "overs": m.group(2),
                        "maidens": m.group(3),
                        "runs": m.group(4),
                        "wickets": m.group(5),
                        "econ": m.group(6)
                    }
    except Exception:
        pass
    return batsmen, bowlers


async def get_live_scorecard_details_async(match_key: str) -> tuple[dict, dict]:
    """Fetch and parse live scorecard details from Crex html page (Async)."""
    batsmen = {}
    bowlers = {}
    try:
        headers = {"User-Agent": HEADERS["User-Agent"], "Referer": "https://crex.com/", "Origin": "https://crex.com"}
        url = f"https://crex.com/cricket-live-score/match-scorecard-{match_key}"
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                html = res.text
                # Batsmen
                bat_pattern = r'<div[^>]*?class="batsman-name".*?<a[^>]*?title="([^"]+)".*?run-highlight">(\d+)</div>.*?class="">(\d+)</div>.*?class="">(\d+)</div>.*?class="">(\d+)</div>.*?class="">([\d.]+)</div>'
                for m in re.finditer(bat_pattern, html, re.DOTALL):
                    name = m.group(1).strip()
                    batsmen[normalize_player_name(name)] = {
                        "runs": m.group(2),
                        "balls": m.group(3),
                        "fours": m.group(4),
                        "sixes": m.group(5),
                        "sr": m.group(6)
                    }
                # Bowlers
                bowl_pattern = r'<div[^>]*?class="bowler-name".*?<a[^>]*?title="([^"]+)".*?run-highlight">([\d.]+)</div>.*?class="">(\d+)</div>.*?class="">(\d+)</div>.*?class="">(\d+)</div>.*?class="">([\d.]+)</div>'
                for m in re.finditer(bowl_pattern, html, re.DOTALL):
                    name = m.group(1).strip()
                    bowlers[normalize_player_name(name)] = {
                        "overs": m.group(2),
                        "maidens": m.group(3),
                        "runs": m.group(4),
                        "wickets": m.group(5),
                        "econ": m.group(6)
                    }
    except Exception:
        pass
    return batsmen, bowlers


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def parse_runs_balls(text: str) -> tuple[int, int, bool]:
    if not text:
        return 0, 0, False
    on_strike = "*" in text
    cleaned = text.replace("*", "")
    parts = cleaned.split(".")
    runs = safe_int(parts[0])
    balls = safe_int(parts[1]) if len(parts) > 1 else 0
    return runs, balls, on_strike


def parse_bowler_stats(text: str) -> dict:
    if not text:
        return None
    parts = text.split(".")
    if len(parts) < 4:
        return None
    return {
        "id": parts[0],
        "balls": safe_int(parts[1]),
        "runs": safe_int(parts[2]),
        "wickets": safe_int(parts[3])
    }


def parse_batsman_stats(text: str) -> dict:
    if not text:
        return None
    parts = text.split(".")
    if len(parts) < 7:
        return None
    return {
        "id": parts[0],
        "runs": safe_int(parts[1]),
        "balls": safe_int(parts[2]),
        "sr": safe_float(parts[3]),
        "fours": safe_int(parts[5]),
        "sixes": safe_int(parts[6])
    }


def convert_balls_to_overs(balls: int) -> str:
    overs = balls // 6
    remaining_balls = balls % 6
    return f"{overs}.{remaining_balls}"


def build_scorecard(
    match_key: str,
    payload: Dict[str, Any],
    player_map: Dict[str, str],
    team_map: Dict[str, Dict[str, str]],
    series_name: str = "",
    sc_batsmen: Dict[str, Any] = None,
    sc_bowlers: Dict[str, Any] = None
) -> Dict[str, Any]:
    teams = parse_teams(payload)
    speech_names = payload.get("speech_names") or {}
    
    # Enrich team names - fall back to speech_names from payload if team_map is incomplete
    for team in teams:
        t_key = team["code"]
        if t_key in team_map and team_map[t_key].get("name"):
            team["name"] = team_map[t_key]["name"]
            team["short"] = team_map[t_key].get("short") or t_key
            team["color_dark"] = team_map[t_key].get("color_dark", "")
            team["color_light"] = team_map[t_key].get("color_light", "")
        else:
            # Fallback to payload speech_names
            team["name"] = speech_names.get(t_key, t_key)
            team["short"] = t_key
            team["color_dark"] = ""
            team["color_light"] = ""

    teams_by_code = {team["code"]: team for team in teams}

    # Determine active batting team code
    batting_code = None
    rb = payload.get("rb") or []
    if rb and isinstance(rb[-1], dict):
        batting_code = clean_team_code(rb[-1].get("bt"))
    if not batting_code:
        batting_code = clean_team_code(payload.get("F"))
        
    batting_team = teams_by_code.get(
        batting_code,
        {"code": batting_code or "UNKNOWN", "name": batting_code or "UNKNOWN", "short": batting_code or "UNKNOWN", "color_dark": "", "color_light": ""},
    )

    # Determine active score & opponent score (first innings)
    k_val = payload.get("k")
    j_val = payload.get("j")
    
    if k_val:
        # Second Innings
        innings_score = normalize_score(k_val)
        opponent_score = normalize_score(j_val)
    else:
        # First Innings
        innings_score = normalize_score(j_val)
        opponent_score = NOT_FOUND

    score = innings_score
    if innings_score != NOT_FOUND:
        score = f"{batting_team['name']} {innings_score}"

    recent_over = parse_recent_over(payload)

    # Parse current batsmen
    batsmen_ids = (payload.get("p") or "").split(".")
    striker_raw = payload.get("q") or ""
    non_striker_raw = payload.get("s") or ""
    current_batsmen = []
    
    s_runs, s_balls, s_on_strike = parse_runs_balls(striker_raw)
    ns_runs, ns_balls, ns_on_strike = parse_runs_balls(non_striker_raw)
    
    if len(batsmen_ids) >= 2:
        id1, id2 = batsmen_ids[0], batsmen_ids[1]
        b1_name = player_map.get(id1, id1)
        b2_name = player_map.get(id2, id2)
        
        # Calculate Strike Rates
        sr1 = f"{(s_runs / s_balls * 100):.2f}" if s_balls > 0 else "0.00"
        sr2 = f"{(ns_runs / ns_balls * 100):.2f}" if ns_balls > 0 else "0.00"
        
        # Determine which score string gets the strike asterisk
        b1_score = f"{s_runs} ({s_balls})"
        if s_on_strike:
            b1_score += "*"
            
        b2_score = f"{ns_runs} ({ns_balls})"
        if ns_on_strike:
            b2_score += "*"
        
        # Determine 4s and 6s from live scorecard details if available
        norm_b1_name = normalize_player_name(b1_name)
        norm_b2_name = normalize_player_name(b2_name)
        
        b1_fours = "--"
        b1_sixes = "--"
        if sc_batsmen and norm_b1_name in sc_batsmen:
            b1_fours = sc_batsmen[norm_b1_name]["fours"]
            b1_sixes = sc_batsmen[norm_b1_name]["sixes"]
            
        b2_fours = "--"
        b2_sixes = "--"
        if sc_batsmen and norm_b2_name in sc_batsmen:
            b2_fours = sc_batsmen[norm_b2_name]["fours"]
            b2_sixes = sc_batsmen[norm_b2_name]["sixes"]
            
        current_batsmen.append({
            "name": b1_name,
            "score": b1_score,
            "fours": b1_fours,
            "sixes": b1_sixes,
            "sr": sr1
        })
        current_batsmen.append({
            "name": b2_name,
            "score": b2_score,
            "fours": b2_fours,
            "sixes": b2_sixes,
            "sr": sr2
        })

    # Parse bowler (Active bowler ID is given by payload key 'b')
    b_id = payload.get("b")
    current_bowler = {}

    if b_id:
        b_name = player_map.get(b_id, b_id)
        norm_b_name = normalize_player_name(b_name)

        # Check if active stats exist in 'y' or 'z'
        y_raw = payload.get("y") or ""
        y_stats = parse_bowler_stats(y_raw)

        z_raw = payload.get("z") or ""
        z_stats = parse_bowler_stats(z_raw)

        active_stats = None
        if y_stats and y_stats["id"] == b_id:
            active_stats = y_stats
        elif z_stats and z_stats["id"] == b_id:
            active_stats = z_stats

        if active_stats:
            if sc_bowlers and norm_b_name in sc_bowlers:
                b_overs = sc_bowlers[norm_b_name]["overs"]
                b_runs = sc_bowlers[norm_b_name]["runs"]
                b_wkts = sc_bowlers[norm_b_name]["wickets"]
                b_econ = sc_bowlers[norm_b_name]["econ"]
                current_bowler = {
                    "name": b_name,
                    "score": f"{b_wkts}-{b_runs} ({b_overs})",
                    "overs": b_overs,
                    "econ": b_econ
                }
            else:
                b_overs = convert_balls_to_overs(active_stats["balls"])
                b_econ = f"{(active_stats['runs'] / (active_stats['balls'] / 6)):.2f}" if active_stats["balls"] > 0 else "0.00"
                current_bowler = {
                    "name": b_name,
                    "score": f"{active_stats['wickets']}-{active_stats['runs']} ({b_overs})",
                    "overs": b_overs,
                    "econ": b_econ
                }
        else:
            # Fallback to HTML scorecard if we don't have socket stats for this bowler yet
            if sc_bowlers and norm_b_name in sc_bowlers:
                b_overs = sc_bowlers[norm_b_name]["overs"]
                b_runs = sc_bowlers[norm_b_name]["runs"]
                b_wkts = sc_bowlers[norm_b_name]["wickets"]
                b_econ = sc_bowlers[norm_b_name]["econ"]
                current_bowler = {
                    "name": b_name,
                    "score": f"{b_wkts}-{b_runs} ({b_overs})",
                    "overs": b_overs,
                    "econ": b_econ
                }
            else:
                current_bowler = {
                    "name": b_name,
                    "score": "0-0 (0.0)",
                    "overs": "0.0",
                    "econ": "0.00"
                }
    else:
        # Fallback if 'b' is completely missing from payload
        y_raw = payload.get("y") or ""
        y_stats = parse_bowler_stats(y_raw)
        z_raw = payload.get("z") or ""
        z_stats = parse_bowler_stats(z_raw)
        
        bowler_stats = y_stats or z_stats
        if bowler_stats:
            b_name = player_map.get(bowler_stats["id"], bowler_stats["id"])
            norm_b_name = normalize_player_name(b_name)
            if sc_bowlers and norm_b_name in sc_bowlers:
                b_overs = sc_bowlers[norm_b_name]["overs"]
                b_runs = sc_bowlers[norm_b_name]["runs"]
                b_wkts = sc_bowlers[norm_b_name]["wickets"]
                b_econ = sc_bowlers[norm_b_name]["econ"]
                current_bowler = {
                    "name": b_name,
                    "score": f"{b_wkts}-{b_runs} ({b_overs})",
                    "overs": b_overs,
                    "econ": b_econ
                }
            else:
                b_overs = convert_balls_to_overs(bowler_stats["balls"])
                b_econ = f"{(bowler_stats['runs'] / (bowler_stats['balls'] / 6)):.2f}" if bowler_stats["balls"] > 0 else "0.00"
                current_bowler = {
                    "name": b_name,
                    "score": f"{bowler_stats['wickets']}-{bowler_stats['runs']} ({b_overs})",
                    "overs": b_overs,
                    "econ": b_econ
                }

    # Last Wicket
    last_wicket_raw = payload.get("x") or ""
    last_wicket_stats = parse_batsman_stats(last_wicket_raw)
    last_wicket = "--"
    if last_wicket_stats:
        lw_name = player_map.get(last_wicket_stats["id"], last_wicket_stats["id"])
        last_wicket = f"{lw_name} {last_wicket_stats['runs']} ({last_wicket_stats['balls']})"

    # Calculate Partnership
    partnership = "--"
    current_score_str = payload.get("k") or payload.get("j") or ""
    match = re.search(r"(\d+)/\d+\s*\(([\d.]+)", current_score_str)
    if match:
        curr_runs = int(match.group(1))
        # Find previous wicket score by scanning rb
        rb = payload.get("rb") or []
        wicket_score = 0
        found = False
        for over in reversed(rb):
            ts = over.get("ts") or ""
            ts_match = re.search(r"(\d+)/\d+", ts)
            if ts_match:
                ts_runs = int(ts_match.group(1))
                balls = over.get("b") or []
                ball_idx = len(balls)
                for ball in reversed(balls):
                    outcome = str(ball.get("u")).strip()
                    if "w" in outcome:
                        runs_after_wicket = sum(safe_int(b.get("t", 0)) for b in balls[ball_idx-1:])
                        wicket_score = ts_runs - runs_after_wicket
                        found = True
                        break
                    ball_idx -= 1
            if found:
                break
        if found:
            part_runs = curr_runs - wicket_score
            partnership = f"{part_runs}"
        else:
            # Fallback to current runs (first wicket partnership)
            partnership = f"{curr_runs}"

    # Calculate CRR / RRR
    crr = "--"
    rrr = "--"
    if match:
        curr_runs = int(match.group(1))
        overs_parts = match.group(2).split(".")
        overs_whole = int(overs_parts[0])
        overs_balls = int(overs_parts[1]) if len(overs_parts) > 1 else 0
        total_balls_bowled = (overs_whole * 6) + overs_balls
        
        if total_balls_bowled > 0:
            crr = f"{(curr_runs / (total_balls_bowled / 6)):.2f}"
            
        # RRR calculation if first innings exists
        first_inn_runs = None
        j_score = payload.get("j")
        if k_val and j_score:
            j_match = re.match(r"^\s*(\d+)", str(j_score))
            if j_match:
                first_inn_runs = int(j_match.group(1))
                
        if first_inn_runs is not None:
            target = first_inn_runs + 1
            runs_needed = target - curr_runs
            
            # Read format overs (default to 20 for T20, 50 for ODI)
            format_str = payload.get("fo") or "T20"
            total_overs = 50 if "ODI" in format_str else 20
            total_format_balls = total_overs * 6
            balls_remaining = total_format_balls - total_balls_bowled
            
            if runs_needed <= 0:
                rrr = "0.00"
            elif balls_remaining > 0:
                rrr = f"{(runs_needed / (balls_remaining / 6)):.2f}"
            else:
                rrr = "N/A"

    # Live Algorithmic Win Probability Simulator
    import math
    win_probability = {}
    
    # Determine team names
    t_keys = list(teams_by_code.keys())
    t1_name = "Team 1"
    t2_name = "Team 2"
    if len(t_keys) >= 2:
        t1_name = teams_by_code[t_keys[0]]["name"]
        t2_name = teams_by_code[t_keys[1]]["name"]

    # Parse current state runs, overs, wickets
    curr_runs = 0
    wickets_lost = 0
    total_balls_bowled = 0
    
    # Read format overs (default to 20 for T20, 50 for ODI)
    format_str = payload.get("fo") or "T20"
    total_overs = 50 if "ODI" in format_str else 20
    total_format_balls = total_overs * 6

    if match:
        curr_runs = int(match.group(1))
        overs_parts = match.group(2).split(".")
        overs_whole = int(overs_parts[0])
        overs_balls = int(overs_parts[1]) if len(overs_parts) > 1 else 0
        total_balls_bowled = (overs_whole * 6) + overs_balls
        
    # Wickets lost
    score_str = payload.get("k") or payload.get("j") or ""
    wkt_match = re.search(r"/(\d+)", score_str)
    if wkt_match:
        wickets_lost = int(wkt_match.group(1))

    # Check if first innings score exists (chase / second innings)
    first_inn_runs = None
    j_score = payload.get("j")
    if k_val and j_score:
        j_match = re.match(r"^\s*(\d+)", str(j_score))
        if j_match:
            first_inn_runs = int(j_match.group(1))

    # Calculate live win probability of batting team
    prob_batting = 50.0

    if first_inn_runs is not None:
        # Second Innings (Chase)
        target = first_inn_runs + 1
        runs_needed = target - curr_runs
        balls_remaining = total_format_balls - total_balls_bowled
        wkts_rem = 10 - wickets_lost
        
        if runs_needed <= 0:
            prob_batting = 100.0
        elif balls_remaining <= 0 or wkts_rem <= 0:
            prob_batting = 0.0
        else:
            baseline_rrr = 5.5 if total_overs == 50 else 8.0
            rrr_val = runs_needed / (balls_remaining / 6)
            rrr_diff = baseline_rrr - rrr_val
            
            game_progress = 1.0 - (balls_remaining / total_format_balls)
            rrr_impact = rrr_diff * (5.0 + 15.0 * game_progress)
            wkt_impact = (wkts_rem - 5) * (1.0 + 9.0 * game_progress)
            
            score_diff = rrr_impact + wkt_impact
            prob_batting = 100.0 / (1.0 + math.exp(-score_diff / 15.0))
            prob_batting = max(1.0, min(99.0, prob_batting))
    else:
        # First Innings
        baseline_rr = 5.0 if total_overs == 50 else 7.5
        crr_val = float(crr) if crr != "--" else baseline_rr
        crr_diff = crr_val - baseline_rr
        
        game_progress = total_balls_bowled / total_format_balls if total_format_balls > 0 else 0.0
        expected_wickets = 10.0 * game_progress
        wkt_diff = expected_wickets - wickets_lost
        
        score_diff = (crr_diff * 4.0) + (wkt_diff * 3.0)
        prob_batting = 50.0 + (score_diff * 5.0)
        prob_batting = max(15.0, min(85.0, prob_batting))

    # Assign back to win_probability matching team orders
    # If batting team is Team 1, prob_batting is team1's probability
    # If batting team is Team 2, prob_batting is team2's probability
    batting_code = batting_team.get("code")
    t1_code = teams[0].get("code") if len(teams) > 0 else ""
    
    if batting_code == t1_code:
        prob1 = prob_batting
        prob2 = 100.0 - prob_batting
    else:
        prob1 = 100.0 - prob_batting
        prob2 = prob_batting

    win_probability = {
        "team1": round(prob1, 2),
        "team2": round(prob2, 2),
        "team1_name": t1_name,
        "team2_name": t2_name
    }

    # Match Title - build a human-readable one from teams + format
    fo = payload.get("fo") or "Match"
    mn = payload.get("mn") or ""
    t_names = [t.get("short") or t.get("name") or t.get("code", "") for t in teams[:2]]
    if len(t_names) == 2 and all(t_names):
        match_no = f" #{mn}" if mn else ""
        match_title = f"{t_names[0]} vs {t_names[1]} {fo}{match_no}"
    elif series_name:
        match_title = series_name
    else:
        match_title = fo or "Cricket Match"

    return {
        "status": "success",
        "source": "crex",
        "match_key": match_key,
        "api_url": build_api_url(match_key),
        "teams": teams,
        "batting_team": batting_team,
        "score": score,
        "innings_score": innings_score,
        "opponent_score": opponent_score,
        "recent_over": recent_over,
        "current_batsmen": current_batsmen,
        "current_bowler": current_bowler,
        "last_wicket": last_wicket,
        "partnership": partnership,
        "crr": crr,
        "rrr": rrr,
        "win_probability": win_probability,
        "title": match_title,
        "series_name": series_name
    }


async def fetch_score_async(match_value: str) -> Dict[str, Any]:
    match_key = extract_match_key(match_value)

    # Scrape mappings first
    player_map, team_map, series_name = await get_match_mappings_async(match_key)

    sc_batsmen, sc_bowlers = {}, {}
    try:
        async def fetch_api():
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(build_api_url(match_key), headers=HEADERS)
                response.raise_for_status()
                return response.json()

        payload, (sc_batsmen, sc_bowlers) = await asyncio.gather(
            fetch_api(),
            get_live_scorecard_details_async(match_key)
        )
    except httpx.TimeoutException as exc:
        raise ScoreFetchError(408, REQUEST_TIMEOUT) from exc
    except httpx.HTTPStatusError as exc:
        raise ScoreFetchError(404, "score data unavailable") from exc
    except httpx.HTTPError as exc:
        raise ScoreFetchError(502, "failed to fetch score data") from exc
    except ValueError as exc:
        raise ScoreFetchError(500, "invalid score response") from exc

    # Force mapping reload if unmapped active player IDs are encountered
    all_ids = set()
    if payload.get("p"):
        all_ids.update(payload.get("p").split("."))
    if payload.get("b"):
        all_ids.add(payload.get("b"))
    if payload.get("y"):
        all_ids.add(payload.get("y").split(".")[0])
    if payload.get("z"):
        all_ids.add(payload.get("z").split(".")[0])

    if any(pid and pid not in player_map for pid in all_ids):
        player_map, team_map, series_name = await get_match_mappings_async(match_key, force=True)

    return build_scorecard(match_key, payload, player_map, team_map, series_name, sc_batsmen, sc_bowlers)


def fetch_score_sync(match_value: str) -> Dict[str, Any]:
    match_key = extract_match_key(match_value)

    # Scrape mappings first
    player_map, team_map, series_name = get_match_mappings_sync(match_key)
    sc_batsmen, sc_bowlers = get_live_scorecard_details_sync(match_key)

    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.get(
                build_api_url(match_key),
                headers=HEADERS,
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise ScoreFetchError(408, REQUEST_TIMEOUT) from exc
    except httpx.HTTPStatusError as exc:
        raise ScoreFetchError(404, "score data unavailable") from exc
    except httpx.HTTPError as exc:
        raise ScoreFetchError(502, "failed to fetch score data") from exc
    except ValueError as exc:
        raise ScoreFetchError(500, "invalid score response") from exc

    # Force mapping reload if unmapped active player IDs are encountered
    all_ids = set()
    if payload.get("p"):
        all_ids.update(payload.get("p").split("."))
    if payload.get("b"):
        all_ids.add(payload.get("b"))
    if payload.get("y"):
        all_ids.add(payload.get("y").split(".")[0])
    if payload.get("z"):
        all_ids.add(payload.get("z").split(".")[0])

    if any(pid and pid not in player_map for pid in all_ids):
        player_map, team_map, series_name = get_match_mappings_sync(match_key, force=True)

    return build_scorecard(match_key, payload, player_map, team_map, series_name, sc_batsmen, sc_bowlers)


def format_score_text(data: Dict[str, Any]) -> str:
    teams = ", ".join(team["name"] for team in data.get("teams", [])) or NOT_FOUND
    recent_over = " ".join(data.get("recent_over", [])) or "N/A"

    return (
        "Live Score\n"
        "|\n"
        f"|-- Match Key   : {data.get('match_key', NOT_FOUND)}\n"
        f"|-- Teams       : {teams}\n"
        f"|-- Batting     : {data.get('batting_team', {}).get('name', NOT_FOUND)}\n"
        f"|-- Score       : {data.get('score', NOT_FOUND)}\n"
        f"|-- Recent Over : {recent_over}"
    )
