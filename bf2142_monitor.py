import json
import os
import urllib.request

API_URL = "https://api.bflist.io/v2/bf2142/servers"
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK"]

PLAYER_THRESHOLD = 10
STATE_FILE = "server_state.json"

def get_servers():
    req = urllib.request.Request(
        API_URL,
        headers={"User-Agent": "BF2142-Server-Monitor"}
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode())

    servers = data.get("servers", [])

    # Handle API pagination
    while data.get("hasMore"):
        cursor = data.get("cursor")
        url = f"{API_URL}?cursor={cursor}"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "BF2142-Server-Monitor"}
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())

        servers.extend(data.get("servers", []))

    return servers


def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def send_discord(server):
    region = server.get("region", "Unknown")
    name = server.get("name", "Unknown server")
    players = server.get("numPlayers", 0)
    max_players = server.get("maxPlayers", 0)
    game_type = server.get("gameType", "Unknown")
    map_name = server.get("mapName", "Unknown")

    mode_names = {
        "gpm_cq": "Conquest",
        "gpm_coop": "Coop",
        "gpm_ti": "Titan",
        "gpm_cp": "Conquest Point"
    }

    mode = mode_names.get(game_type, game_type)

    message = (
        f"**BF2142 SERVER ALERT**\n"
        f"**{region} — {mode}**\n"
        f"Server: **{name}**\n"
        f"Players: **{players}/{max_players}**\n"
        f"Map: **{map_name}**"
    )

    payload = json.dumps({"content": message}).encode("utf-8")

    req = urllib.request.Request(
        WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=30):
        pass


def main():
    servers = get_servers()
    previous = load_state()
    current = {}

    for server in servers:
        game_type = server.get("gameType", "")
        region = server.get("region", "")

        # Only US and EU
        if region not in ("US", "EU"):
            continue

        # Never alert for Titan
        if game_type == "gpm_ti":
            continue

        server_id = server.get("guid") or (
            f"{server.get('ip')}:{server.get('port')}"
        )

        players = server.get("numPlayers", 0)

        current[server_id] = players

        previous_players = previous.get(server_id, 0)

        # Alert only when crossing the threshold upward
        if previous_players < PLAYER_THRESHOLD and players >= PLAYER_THRESHOLD:
            send_discord(server)

    save_state(current)


if __name__ == "__main__":
    main()
