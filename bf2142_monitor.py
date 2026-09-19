import json
import os
import urllib.request

PLAYER_THRESHOLD = 10

TARGET_SERVERS = {
    "Reclamation EU": "EU",
    "Reclamation US": "US",
}

API_BASE = "https://api.bflist.io/v2/bf2142"
SERVERS_URL = f"{API_BASE}/servers"

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK"]
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

STATE_FILE = "server_state.json"

MODE_NAMES = {
    "gpm_cq": "Conquest",
    "gpm_coop": "Coop",
    "gpm_cp": "Conquest Point",
    "gpm_ti": "Titan",
    "gpm_al": "Assault Lines",
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


def get_all_servers():
    servers = []
    url = SERVERS_URL

    while url:
        data = api_get(url)

        servers.extend(data.get("servers", []))

        if data.get("hasMore") and data.get("cursor"):
            cursor = data["cursor"]
            url = f"{SERVERS_URL}?cursor={cursor}"
        else:
            url = None

    return servers


def find_target_servers():
    all_servers = get_all_servers()
    found = {}

    for server in all_servers:
        name = server.get("name", "").strip()

        if name in TARGET_SERVERS:
            found[name] = server

    return found


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


def send_ntfy(message):
    clean_message = message.replace("**", "")

    request = urllib.request.Request(
        NTFY_URL,
        data=clean_message.encode("utf-8"),
        headers={
            "Title": "BF2142 Server Alert",
            "Priority": "high",
            "Tags": "video_game,rotating_light",
            "Content-Type": "text/plain; charset=utf-8",
            "User-Agent": "BF2142-Server-Monitor/1.0",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status not in (200, 201):
            raise RuntimeError(
                f"ntfy returned HTTP {response.status}"
            )


def send_alert(message):
    discord_error = None
    ntfy_error = None

    try:
        send_discord(message)
        print("  Discord alert sent.")
    except Exception as error:
        discord_error = error
        print(f"  Discord ERROR: {error}")

    try:
        send_ntfy(message)
        print("  ntfy alert sent.")
    except Exception as error:
        ntfy_error = error
        print(f"  ntfy ERROR: {error}")

    if discord_error and ntfy_error:
        raise RuntimeError(
            f"Both notification services failed. "
            f"Discord: {discord_error}; "
            f"ntfy: {ntfy_error}"
        )


def send_test_alert():
    discord_message = (
        "**BF2142 SERVER MONITOR TEST**\n"
        "Discord and ntfy alerts are configured correctly."
    )

    ntfy_message = (
        "BF2142 SERVER MONITOR TEST\n"
        "Discord and ntfy alerts are configured correctly."
    )

    send_discord(discord_message)
    print("Discord test alert sent.")

    send_ntfy(ntfy_message)
    print("ntfy test alert sent.")


def main():
    if os.environ.get("TEST_ALERT", "").lower() == "true":
        send_test_alert()
        return

    previous_state = load_state()
    current_state = {}

    print("Finding current Reclamation servers...")

    servers = find_target_servers()

    print(
        f"Found {len(servers)} of "
        f"{len(TARGET_SERVERS)} target servers."
    )

    for server_name, region in TARGET_SERVERS.items():

        if server_name not in servers:
            print(
                f"ERROR: {server_name} "
                f"was not found in the bflist server list."
            )
            continue

        server = servers[server_name]

        ip = server.get("ip", "Unknown")
        port = server.get("port", "Unknown")
        players = int(server.get("numPlayers", 0))
        max_players = int(server.get("maxPlayers", 64))
        map_name = server.get("mapName", "Unknown")
        actual_name = server.get("name", server_name)

        # The list endpoint does not always include gameType,
        # so query the individual server for complete data.
        server_url = f"{API_BASE}/servers/{ip}:{port}"
        detailed_server = api_get(server_url)

        players = int(
            detailed_server.get("numPlayers", players)
        )
        max_players = int(
            detailed_server.get("maxPlayers", max_players)
        )
        game_type = detailed_server.get("gameType", "")
        map_name = detailed_server.get(
            "mapName",
            map_name
        )
        actual_name = detailed_server.get(
            "name",
            actual_name
        )

        mode = MODE_NAMES.get(
            game_type,
            game_type or "Unknown"
        )

        print(
            f"{region} | {actual_name} | "
            f"{ip}:{port} | "
            f"{players}/{max_players} | "
            f"{mode} | {map_name}"
        )

        # Never alert on Titan.
        if game_type == "gpm_ti":
            print("  Titan detected. Ignoring.")
            continue

        # Alert when the server reaches the threshold.
        if players >= PLAYER_THRESHOLD:

            current_state[server_name] = {
                "players": players,
                "mode": mode,
            }

            was_already_alerted = (
                server_name in previous_state
            )

            if not was_already_alerted:

                message = (
                    f"**BF2142 SERVER ALERT**\n"
                    f"**{region} — {mode}**\n"
                    f"Server: **{actual_name}**\n"
                    f"Players: **{players}/{max_players}**\n"
                    f"Map: **{map_name}**"
                )

                send_alert(message)

                print("  ALERT SENT.")

            else:
                print(
                    "  Already alerted. "
                    "No duplicate alert."
                )

        else:
            print(
                f"  Below threshold "
                f"({players} < {PLAYER_THRESHOLD})."
            )

    if current_state != previous_state:
        save_state(current_state)
        print("Server state changed and was saved.")
    else:
        print("No state change.")


if __name__ == "__main__":
    main()
