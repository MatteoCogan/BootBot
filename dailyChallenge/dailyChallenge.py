import discord
import asyncio
import os
import json
import subprocess
import re
from datetime import datetime
import pycountry
from geoguessr_async import Geoguessr
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["BOT_TOKEN"]
GEOGUESSR_TOKEN = os.environ["GEOGUESSR_TOKEN"]
SCORES_PATH = "dailyChallenge/scores.json"
CONFIG_PATH = "dailyChallenge/config.json"
USERS_PATH = "dailyChallenge/users_mapping.json"

POINTS_BY_RANK = [4, 3, 2]


def get_country_flag(country_name):
    try:
        country = pycountry.countries.lookup(country_name)
        code = country.alpha_2.upper()
        return chr(127397 + ord(code[0])) + chr(127397 + ord(code[1]))
    except LookupError:
        return ""


def get_discord_mention(player_id: str, users: list) -> str:
    for user in users:
        if user["userId"] == player_id:
            return user["discordId"]
    return None


def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def update_scores_json(country, players):
    scores = load_json(SCORES_PATH)

    if country not in scores:
        scores[country] = []

    for i, player in enumerate(players):
        pts = POINTS_BY_RANK[i] if i < len(POINTS_BY_RANK) else 1
        scores[country].append({"pts": pts, "user": player["userId"]})

    with open(SCORES_PATH, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2, ensure_ascii=False)

    print(f"[✓] Scores mis à jour pour {country}")
    return scores


def generate_result_message(country, players, global_scores, new_link):
    flag = get_country_flag(country)
    today = datetime.utcnow().strftime("%d")

    msg = f"{flag}  Daily Challenge {today} - Résultats\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, p in enumerate(players[:3]):
        msg += f"{medals[i]} {p['mention']}\n"

    msg += f"\n{flag}  Classement général - Provisoire\n"

    leaderboard = {}
    for entry in global_scores.get(country, []):
        leaderboard[entry["user"]] = leaderboard.get(entry["user"], 0) + entry["pts"]

    sorted_leaderboard = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
    symbols = ["🥇", "🥈", "🥉", "🍫"]
    for i, (user, pts) in enumerate(sorted_leaderboard[:4]):
        msg += f"{symbols[i]} {user} - {pts}pts\n"

    msg += f"\n{flag}  Daily Challenge {int(today)+1} - Nouveau lien :\n{new_link}"
    return msg


async def process_game_data(client: Geoguessr, link, users):
    print(f"[✓] Récupération des données de la partie : {link}")
    game_data = await client.get_challenge_score(link)
    if not game_data:
        print(f"[✗] Aucune donnée de partie trouvée pour le lien : {link}")
        return []

    print(f"[✓] Données de partie récupérées : {len(game_data)} joueurs")

    players = []
    for game in game_data:
        player_id = getattr(game, "userId", None)
        score = getattr(game, "gamePlayerTotalscoreAmount", 0)
        player_name = getattr(game, "playerName", "Joueur inconnu")

        mention = get_discord_mention(player_id, users)
        display_name = mention if mention else player_name

        players.append({
            "userId": player_id,       # ID stable utilisé pour le score
            "mention": display_name,   # Pour affichage Discord
            "score": score
        })

    players.sort(key=lambda x: x["score"] or 0, reverse=True)
    print(f"[✓] Joueurs triés par score : {[p['userId'] for p in players]}")
    return players


def push_scores():
    subprocess.run(["git", "add", SCORES_PATH])
    subprocess.run(["git", "commit", "-m", f"update scores {datetime.today().strftime('%Y-%m-%d')}"])
    subprocess.run(["git", "push"])
    print("[✓] Scores push sur GitHub")


async def main():
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"[✓] Connecté en tant que {client.user}")
        config = load_json(CONFIG_PATH)
        users = load_json(USERS_PATH)
        scores = load_json(SCORES_PATH)

        time_limit = config.get("time-limit", 60)
        country_entries = config.get("country", [])

        geo_client = Geoguessr(GEOGUESSR_TOKEN)
        print("[✓] Client Geoguessr initialisé")
        for entry in country_entries:
            country_name = entry["name"]
            channel_id = int(entry["channel_id"])
            map_url = entry["map_url"]

            channel = client.get_channel(channel_id)
            if not channel:
                continue
            if not channel.permissions_for(channel.guild.me).send_messages:
                print(f"[✗] Permissions insuffisantes pour envoyer des messages dans le channel {channel.name}.")
                continue

            last_challenge_url = None
            async for msg in channel.history(limit=20):
                urls = re.findall(r'(https?://www\.geoguessr\.com/challenge/\S+?)(?=\s|$|>)', msg.content)
                if urls:
                    last_challenge_url = urls[0]
                    break

            if not last_challenge_url:
                print(f"[✗] Aucun lien trouvé dans le channel {channel_id}.")
                continue
            else:
                print(f"[✓] Lien trouvé : {last_challenge_url}")

            players = await process_game_data(geo_client, last_challenge_url, users)
            scores = update_scores_json(country_name, players)
            
            new_link=last_challenge_url
            # new_link = await geo_client.generate_challenge(
            #     map_url, move=False, timeLimit=time_limit, play_map=False
            # )

            message = generate_result_message(country_name, players, scores, new_link)
            await channel.send(message)

        await client.close()
        push_scores()

    await client.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())