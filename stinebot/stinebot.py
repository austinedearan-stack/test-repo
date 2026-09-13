"""
Stinebot
------------------------
A feature-rich Discord bot built with discord.py supporting both SLASH COMMANDS 
and PREFIX COMMANDS (mention or ! prefix).

Features added:
  - Smart Mention Responses & Conversational Context (time, birthday setup)
  - Member Online & Activity Tracking (Games, Spotify, Streams)
  - Server Event Tracking
  - Role Listing & Role Management
  - User Mention Tracker (Pinglist)
  - Image to GIF Converter
  - AFK & Birthday Systems
  - User Spy & Celebrate Commands
  - Ask Someone Out & Bored (Fun Fact) Commands
  - Web Search Features: Factcheck & Kenyan News
  - Terminal Control Panel (Send messages into Discord channels as the bot)
"""

import os
import io
import json
import time
import random
import asyncio
from datetime import datetime
from collections import deque

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from PIL import Image

# ---------------------------------------------------------------------------
# 1. SETUP & INTENTS
# ---------------------------------------------------------------------------

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

# Prefix support: allows commands via slash, prefix (!), or direct mention
def get_prefix(bot, message):
    return commands.when_mentioned_or("!")(bot, message)

bot = commands.Bot(command_prefix=get_prefix, intents=intents)

# In-memory storage for AFK status & Mention History (Pinglist)
afk_users = {}       # {user_id: reason}
mention_history = {} # {user_id: [list of mention strings]}

# ---------------------------------------------------------------------------
# 2. DATA PERSISTENCE (Settings & Birthdays)
# ---------------------------------------------------------------------------

DATA_FILE = os.path.join(os.path.dirname(__file__), "stinebot_data.json")

def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {"birthdays": {}, "greetings": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# ---------------------------------------------------------------------------
# 3. EVENT HANDLERS & BOT BACKEND CHAT
# ---------------------------------------------------------------------------

BACKSTORY = (
    "Niaje! Mimi ni **Stinebot** 🤖🇰🇪 — ready to keep the server active, "
    "check up on members, handle roles, and bring top Nairobi vibes."
)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"⚠️ Failed to sync commands: {e}")
    
    # Start backend terminal chat in background
    bot.loop.create_task(terminal_backend_chat())

async def terminal_backend_chat():
    """Terminal Backend: Allows typing messages directly in console to send to Discord."""
    await bot.wait_until_ready()
    print("\n--- STINEBOT BACKEND CHAT ACTIVE ---")
    print("Format to send message: <channel_id> <your message>")
    print("Example: 123456789012345678 Hello server!\n")
    
    while not bot.is_closed():
        try:
            user_input = await bot.loop.run_in_executor(None, input)
            if not user_input.strip():
                continue
            parts = user_input.split(" ", 1)
            if len(parts) < 2:
                print("❌ Invalid format! Use: <channel_id> <message>")
                continue
            
            channel_id, msg_text = int(parts[0]), parts[1]
            channel = bot.get_channel(channel_id)
            if channel:
                await channel.send(msg_text)
                print(f"✅ Sent to #{channel.name}")
            else:
                print("❌ Channel not found or bot lacks access.")
        except Exception as e:
            print(f"⚠️ Chat Error: {e}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # --- AFK Alert & Removal ---
    if message.author.id in afk_users:
        del afk_users[message.author.id]
        await message.channel.send(f"Welcome back {message.author.mention}, I removed your AFK status!")

    for user in message.mentions:
        if user.id in afk_users:
            await message.channel.send(f"📌 {user.display_name} is currently AFK: {afk_users[user.id]}")

    # --- Pinglist Logger ---
    for mentioned_user in message.mentions:
        mention_history.setdefault(mentioned_user.id, []).append(
            f"From **{message.author.display_name}** in {message.channel.mention}: {message.content[:100]}"
        )
    for role in message.role_mentions:
        for member in role.members:
            mention_history.setdefault(member.id, []).append(
                f"Role ping ({role.name}) by **{message.author.display_name}** in {message.channel.mention}"
            )

    # --- Neutral Responses & Conversational Context ---
    if bot.user in message.mentions:
        clean_content = message.content.replace(f"<@{bot.user.id}>", "").strip().lower()
        
        if not clean_content:
            neutral_replies = [
                f"Niaje {message.author.mention}? I'm here!",
                f"Umelike kuping Stinebot {message.author.mention}? What's up?",
                f"Yes {message.author.mention}? Need help with commands? Try `/` or `!`",
            ]
            await message.channel.send(random.choice(neutral_replies))
        elif "time" in clean_content:
            now_time = datetime.now().strftime("%H:%M:%S (%I:%M %p)")
            await message.channel.send(f"🕒 The current server time is **{now_time}**.")
        elif "set birthday" in clean_content or "birthday" in clean_content:
            await message.channel.send("🎉 You can set your birthday using the command `/setbirthday YYYY-MM-DD` or `!setbirthday YYYY-MM-DD`!")
        elif "who are you" in clean_content or "about" in clean_content:
            await message.channel.send(BACKSTORY)

    await bot.process_commands(message)

# ---------------------------------------------------------------------------
# 4. GIPHY FETCHING UTILITY
# ---------------------------------------------------------------------------

GIPHY_URL = "https://api.giphy.com/v1/gifs/search"

async def fetch_gif(query: str) -> str:
    if not GIPHY_API_KEY:
        return "https://media.tenor.com/2roX3-VC10YAAAAC/slap-anime.gif"
    params = {"q": query, "api_key": GIPHY_API_KEY, "limit": 10, "rating": "pg-13"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(GIPHY_URL, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("data", [])
                    if results:
                        return random.choice(results)["images"]["original"]["url"]
    except Exception:
        pass
    return "https://media.tenor.com/9wF9k7X4Uz4AAAAC/anime-hug.gif"

# ---------------------------------------------------------------------------
# 5. SERVER / MEMBER STATUS & EVENTS
# ---------------------------------------------------------------------------

@bot.hybrid_command(name="online", description="See online status of members in server or current channel")
async def online_status(ctx: commands.Context):
    members = ctx.channel.members if ctx.guild else []
    online = [m.display_name for m in members if m.status != discord.Status.offline and not m.bot]
    
    embed = discord.Embed(title=f"Online Members in #{ctx.channel.name}", color=discord.Color.green())
    embed.add_field(name=f"Total Active ({len(online)})", value=", ".join(online) if online else "No online members found.")
    await ctx.send(embed=embed)

@bot.hybrid_command(name="spy", description="Spy on a user's current activity (Games, Music, Streams)")
async def spy(ctx: commands.Context, member: discord.Member):
    if not member.activities:
        await ctx.send(f"🕵️ **{member.display_name}** is currently not doing any tracked activity.")
        return

    act_list = []
    for act in member.activities:
        if isinstance(act, discord.Spotify):
            act_list.append(f"🎵 **Listening to Spotify**: {act.title} by {act.artist}")
        elif isinstance(act, discord.Game):
            act_list.append(f"🎮 **Playing**: {act.name}")
        elif isinstance(act, discord.Streaming):
            act_list.append(f"📹 **Streaming**: [{act.name}]({act.url})")
        elif act.type == discord.ActivityType.custom:
            act_list.append(f"💬 **Custom Status**: {act.name}")

    embed = discord.Embed(title=f"🕵️ Activity Details: {member.display_name}", color=discord.Color.purple())
    embed.description = "\n".join(act_list) if act_list else "Doing something custom/unknown."
    await ctx.send(embed=embed)

@bot.hybrid_command(name="events", description="List active or upcoming server events")
async def list_events(ctx: commands.Context):
    if not ctx.guild:
        return
    events = ctx.guild.scheduled_events
    if not events:
        await ctx.send("📅 No scheduled events found in this server.")
        return

    embed = discord.Embed(title=f"📅 Scheduled Events in {ctx.guild.name}", color=discord.Color.blue())
    for ev in events:
        embed.add_field(
            name=ev.name,
            value=f"**Start**: {ev.start_time.strftime('%Y-%m-%d %H:%M')}\n**Description**: {ev.description or 'N/A'}",
            inline=False
        )
    await ctx.send(embed=embed)

# ---------------------------------------------------------------------------
# 6. ROLE MANAGEMENT & PINGLIST
# ---------------------------------------------------------------------------

@bot.hybrid_command(name="roles", description="List all server roles")
async def list_roles(ctx: commands.Context):
    roles = [role.name for role in ctx.guild.roles if role.name != "@everyone"]
    embed = discord.Embed(title="📜 Server Roles", description=", ".join(roles), color=discord.Color.gold())
    await ctx.send(embed=embed)

@bot.hybrid_command(name="giverole", description="Give a role to a member (Admin)")
@commands.has_permissions(manage_roles=True)
async def give_role(ctx: commands.Context, member: discord.Member, role: discord.Role):
    await member.add_roles(role)
    await ctx.send(f"✅ Added role **{role.name}** to {member.mention}.")

@bot.hybrid_command(name="pinglist", description="See recent mentions of you or your roles")
async def pinglist(ctx: commands.Context):
    history = mention_history.get(ctx.author.id, [])
    if not history:
        await ctx.send("📥 You have no logged pings yet!")
        return

    embed = discord.Embed(title=f"📥 Ping History for {ctx.author.display_name}", color=discord.Color.blue())
    embed.description = "\n".join(history[-10:])  # Show latest 10
    await ctx.send(embed=embed)

# ---------------------------------------------------------------------------
# 7. UTILITY & FUN COMMANDS
# ---------------------------------------------------------------------------

@bot.hybrid_command(name="afk", description="Set your AFK status")
async def set_afk(ctx: commands.Context, reason: str = "Away from keyboard"):
    afk_users[ctx.author.id] = reason
    await ctx.send(f"💤 {ctx.author.mention} is now AFK: {reason}")

@bot.hybrid_command(name="setbirthday", description="Set your birthday (YYYY-MM-DD)")
async def set_birthday(ctx: commands.Context, date_str: str):
    data = load_data()
    data["birthdays"][str(ctx.author.id)] = date_str
    save_data(data)
    await ctx.send(f"🎂 Birthday set to **{date_str}** for {ctx.author.mention}!")

@bot.hybrid_command(name="celebrate", description="Celebrate a user with a GIF")
async def celebrate(ctx: commands.Context, member: discord.Member):
    gif = await fetch_gif("celebrate party anime")
    embed = discord.Embed(title="🎉 Celebration Time!", description=f"Let's celebrate {member.mention}! 🥳", color=discord.Color.magenta())
    embed.set_image(url=gif)
    await ctx.send(embed=embed)

@bot.hybrid_command(name="askout", description="Ask someone out on a date!")
async def ask_out(ctx: commands.Context, member: discord.Member):
    gif = await fetch_gif("anime romance shy blush")
    embed = discord.Embed(
        title="💌 Someone has a crush!",
        description=f"{ctx.author.mention} is asking {member.mention} out on a date! What do you say? 😳👉👈",
        color=discord.Color.pink()
    )
    embed.set_image(url=gif)
    await ctx.send(embed=embed)

@bot.hybrid_command(name="bored", description="Get a fun random fact")
async def bored(ctx: commands.Context):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://uselessfacts.jsph.pl/api/v2/facts/random") as resp:
            if resp.status == 200:
                data = await resp.json()
                await ctx.send(f"💡 **Fun Fact**: {data.get('text')}")
            else:
                await ctx.send("💡 **Fun Fact**: Honey never spoils. 3,000-year-old honey in Egyptian tombs is still edible!")

@bot.hybrid_command(name="factcheck", description="Search Google / Web for quick answer")
async def factcheck(ctx: commands.Context, query: str):
    # Uses DuckDuckGo instant answer query
    url = f"https://api.duckduckgo.com/?q={query}&format=json"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            answer = data.get("AbstractText")
            if answer:
                await ctx.send(f"🔍 **Fact Check Results**: {answer}")
            else:
                await ctx.send(f"🔍 Couldn't find instant match. Check directly: https://www.google.com/search?q={query.replace(' ', '+')}")

@bot.hybrid_command(name="news", description="Lookup current Kenyan news headlines")
async def news(ctx: commands.Context):
    url = "https://newsapi.org/v2/top-headlines?country=ke&apiKey=YOUR_NEWSAPI_KEY"
    # Fallback simulation if no news key is present:
    embed = discord.Embed(title="🇰🇪 Current Kenyan News Headlines", color=discord.Color.red())
    embed.add_field(name="1. Daily Nation", value="[Read Latest Nation News](https://nation.africa/kenya)", inline=False)
    embed.add_field(name="2. Standard Digital", value="[Read Latest Standard News](https://www.standardmedia.co.ke/)", inline=False)
    await ctx.send(embed=embed)

@bot.hybrid_command(name="togif", description="Convert attached image/PNG to GIF")
async def togif(ctx: commands.Context, attachment: discord.Attachment):
    if not attachment.content_type or "image" not in attachment.content_type:
        await ctx.send("❌ Please attach a valid image file.")
        return

    await ctx.defer()
    img_bytes = await attachment.read()
    img = Image.open(io.BytesIO(img_bytes))

    out_buffer = io.BytesIO()
    img.save(out_buffer, format="GIF", save_all=True)
    out_buffer.seek(0)

    file = discord.File(fp=out_buffer, filename="converted.gif")
    await ctx.send(content="✨ Here is your converted GIF:", file=file)

# ---------------------------------------------------------------------------
# 8. RUN BOT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("❌ No DISCORD_TOKEN found in .env file.")
    bot.run(TOKEN)
