import discord
import asyncio
import os
import json
from datetime import datetime
import subprocess
import re
import pycountry

TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID1 = int(os.environ["CHANNEL_ID1"])
CHANNEL_ID2 = int(os.environ["CHANNEL_ID2"])

SCORES_PATH = "scores.json"

# Points par rang
POINTS_BY_RANK = [15, 10, 5]

def get_country_flag(country_name: str) -> str:
    """
    Retourne l'emoji drapeau correspondant au nom de pays fourni.
    Si non trouvé, retourne une chaîne vide.
    """
    try:
        # Recherche par nom exact
        country = pycountry.countries.lookup(country_name)
        code = country.alpha_2.upper()
        return chr(127397 + ord(code[0])) + chr(127397 + ord(code[1]))
    except LookupError:
        return ""

def update_scores_json(country, players):
    if not os.path.exists(SCORES_PATH):
        scores = {}
    else:
        with open(SCORES_PATH, "r", encoding="utf-8") as f:
            scores = json.load(f)

    if country not in scores:
        scores[country] = []

    for i, user in enumerate(players):
        if i >= len(POINTS_BY_RANK):
            break
        entry = {"pts": POINTS_BY_RANK[i], "user": user}
        scores[country].append(entry)

    with open(SCORES_PATH, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2, ensure_ascii=False)

    print(f"[✓] Scores mis à jour pour {country}")

def push_scores():
    subprocess.run(["git", "add", SCORES_PATH])
    subprocess.run(["git", "commit", "-m", f"update scores {datetime.today().strftime('%Y-%m-%d')}"])
    subprocess.run(["git", "push"])
    print("[✓] Scores push sur GitHub")

async def main():
    intents = discord.Intents.default()
    intents.messages = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"[✓] Connecté en tant que {client.user}")

        for CHANNEL_ID in [CHANNEL_ID1, CHANNEL_ID2]:
            channel = client.get_channel(CHANNEL_ID)
            if not channel:
                print(f"[✗] Salon {CHANNEL_ID} introuvable.")
                continue

            async for msg in channel.history(limit=20):
                if msg.author == client.user:
                    country, players = extract_country_and_scores(msg.content)
                    if country and players:
                        update_scores_json(country, players)
                        break

        await client.close()
        push_scores()

    await client.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
