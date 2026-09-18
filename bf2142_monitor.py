import json
import os
import urllib.request
import urllib.error

PLAYER_THRESHOLD = 10

SERVERS = {
    "Reclamation EU": {
        "ip": "95.179.130.30",
        "port": 17567,
        "region": "EU",
    },
    "Reclamation US": {
        "ip": "107.191.58.111",
        "port": 17567,
        "region": "US",
    },
}

API_BASE = "https://api.bflist.io/v2/bf2142/servers"
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK"]
STATE_FILE = "server_state.json"

MODE_NAMES = {
    "gpm_cq": "Conquest",
    "gpm_coop": "Coop",
    "gpm_cp": "Conquest Point",
    "gpm_ti": "Titan",
}


def api_get(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "BF2142-Server-Monitor/1.0"
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def get_server(server):
    url = f"{API_BASE}/{server['ip']}:{server['port']}"
    return api_get(url)


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(state, file, indent=2, sort_keys=True)
        file.write("\n")


def send_discord(message):
    payload = json.dumps({
        "content": message
    }).encode("utf-8")

    request = urllib.request.Request(
        WEBHOOK_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "BF2142-Server-Monitor/1.0",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status not in (200, 204):
            raise RuntimeError(
                f"Discord returned HTTP {response.status}"
            )


def send_test_alert():
    message = (
        "**BF2142 SERVER MONITOR TEST**\n"
        "Discord alerts are configured correctly."
    )

    send_discord(message)
    print("Test Discord alert sent successfully.")


def main():
    if os.environ.get("TEST_ALERT", "").lower() == "true":
        send_test_alert()
        return

    previous_state = load_state()
    current_state = {}

    for server_name, server_config in SERVERS.items():
        print(f"Checking {server_name}...")

        try:
            server = get_server(server_config)

            players = int(server.get("numPlayers", 0))
            max_players = int(server.get("maxPlayers", 64))
            game_type = server.get("gameType", "")
            map_name = server.get("mapName", "Unknown")
            actual_name = server.get("name", server_name)

            mode = MODE_NAMES.get(game_type, game_type or "Unknown")

            print(
                f"  {actual_name}: "
                f"{players}/{max_players}, "
                f"{mode}, map={map_name}"
            )

            # Never alert on Titan.
            if game_type == "gpm_ti":
                print("  Titan detected. Ignoring.")
                continue

            # Only alert when the server reaches the threshold.
            if players >= PLAYER_THRESHOLD:

                current_state[server_name] = {
                    "players": players,
                    "mode": mode,
                }

                was_already_alerted = server_name in previous_state

                if not was_already_alerted:
                    message = (
                        f"**BF2142 SERVER ALERT**\n"
                        f"**{server_config['region']} — {mode}**\n"
                        f"Server: **{actual_name}**\n"
                        f"Players: **{players}/{max_players}**\n"
                        f"Map: **{map_name}**"
                    )

                    send_discord(message)
                    print("  ALERT SENT.")

                else:
                    print("  Already alerted. No duplicate alert.")

            else:
                print(
                    f"  Below threshold "
                    f"({players} < {PLAYER_THRESHOLD})."
                )

        except Exception as error:
            print(f"  ERROR checking {server_name}: {error}")
            raise

    if current_state != previous_state:
        save_state(current_state)
        print("Server state changed and was saved.")
    else:
        print("No state change.")


if __name__ == "__main__":
    main()
