import os
import io
import re
import unicodedata
import glob
import json
import math
import time
import random
import asyncio
import datetime
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops, features
    PIL_OK = True
    try:
        RAQM = features.check("raqm")  # لو موجود، Pillow يرتب العربي بنفسه
    except Exception:
        RAQM = False
except ImportError:
    PIL_OK = False
    RAQM = False

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    RESHAPE_OK = True
except ImportError:
    RESHAPE_OK = False

# ============================================================
#                        الإعدادات
# ============================================================
TOKEN = os.environ["DISCORD_TOKEN"]  # التوكن من متغيرات البيئة، لا تكتبه بالكود
DATA_FILE = "data.json"
BRAND = "NEXUS GAMING"
BOT_VERSION = "12 (levels+bank+shop+memes)"

# أسماء ثابتة (الرتب والأقسام)
MEMBER_ROLE = "عضو"
MOD_ROLE = "🛡 مشرف"
SUPPORT_CATEGORY = "الدعم"
ADMIN_CATEGORY = "الإدارة"
CREATOR_VC = "➕ أنشئ غرفتك"
GAME_ROLES = ["🎮 ماينكرافت", "🔫 ببجي", "🕹 ألعاب أخرى"]
LEVEL_ROLES = {5: "⭐ عضو مميز"}  # مستوى: رتبة
LINK_CHANNELS = {"الميمز", "المونتاج", "الفيديوهات", "البث-المباشر", "ترويج-الحسابات", "لقطات",
                 "تصاميم-الأعضاء", "أخبار-الكرة", "الأخبار", "ملفات-ببجي", "سيرفرات-ماينكرافت",
                 "سيرفرات-فايف-ام"}  # الروابط مسموحة فيها
XP_COOLDOWN = 60

# متجر الرتب: الاسم -> السعر
SHOP = {"⭐ عضو مميز": 500, "🎮 جيمر محترف": 800, "💎 VIP": 1000, "🌈 ملوّن": 1500,
        "🔥 أسطورة": 3000, "👑 ملك السيرفر": 10000, "🧹 مسح تحذير": 300}
SHOP_COLOURS = {"⭐ عضو مميز": discord.Colour.gold(), "🎮 جيمر محترف": discord.Colour.green(),
                "💎 VIP": discord.Colour.teal(), "🌈 ملوّن": discord.Colour.magenta(),
                "🔥 أسطورة": discord.Colour.dark_orange(), "👑 ملك السيرفر": discord.Colour.from_rgb(255, 215, 0)}

# إعدادات قابلة للتغيير من /config_set
DEFAULT_CONFIG = {
    "welcome_channel": "الترحيب",
    "log_channel": "السجل",
    "level_channel": "المستوى",
    "daily_channel": "المكافأة-اليومية",
    "shop_channel": "المتجر",
    "balance_channel": "الأرصدة",
    "leaderboard_channel": "المتصدرون",
    "games_channel": "ألعاب-مصغرة",
    "trivia_channel": "المسابقات",
    "poll_channel": "اقتراحات-الأعضاء",
    "events_channel": "الفعاليات",
    "tournament_channel": "تسجيل-البطولة",
    "news_channel": "الأخبار",
    "mcserver_channel": "سيرفرات-ماينكرافت",
    "staff_tickets_channel": "طلبات-الدعم",
    "commands_channel": "الأوامر",
    "meme_channel": "الميمز",
    "dhikr_channel": "التسبيح",
    "new_account_days": "3",
    "max_warns": "3",
    "mc_ip": "",
    "automod": "on",
}

ROLES_TO_CREATE = [
    (MOD_ROLE, discord.Colour.red(),
     discord.Permissions(kick_members=True, ban_members=True, moderate_members=True,
                         manage_messages=True, manage_channels=True), True),
    ("⭐ عضو مميز", discord.Colour.gold(), discord.Permissions.none(), True),
    (MEMBER_ROLE, discord.Colour.light_grey(), discord.Permissions.none(), False),
    (GAME_ROLES[0], discord.Colour.green(), discord.Permissions.none(), False),
    (GAME_ROLES[1], discord.Colour.orange(), discord.Permissions.none(), False),
    (GAME_ROLES[2], discord.Colour.blue(), discord.Permissions.none(), False),
]

# التصميم: كل قسم = (الاسم العربي، الإنجليزي للزخرفة، الرمز، [رومات كتابية], [رومات صوتية])
# الأقسام من 1 إلى 9 مأخوذة من سيرفرك، ومن 10 إلى 14 إضافة مني
SPEC = [
    ("معلومات", "INFO", "⚜",
     [("الترحيب", "Welcome"), ("القوانين", "Rules"), ("الأخبار", "News"), ("المتصدرون", "Leaderboard")], []),
    ("الدردشة", "CHAT", "✾",
     [("الدردشة", "Chat"), ("الأوامر", "Commands"), ("الميمز", "Memes"), ("المونتاج", "Edits"),
      ("المستوى", "Level"), ("اقتراحات-الأعضاء", "Ideas")], []),
    ("الصوتيات", "VOICE", "♛", [],
     [("الموسيقى", "Music"), ("المقهى", "Cafe"), ("البث", "Stream"), ("الاجتماعات", "Meeting"),
      ("المالك", "Owner"), (CREATOR_VC, "Create")]),
    ("القرآن الكريم", "QURAN", "☪",
     [("التوعية-الدينية", "Awareness"), ("التسبيح", "Tasbeeh")], []),
    ("الفعاليات", "EVENTS", "🜲",
     [("قوانين-الفعاليات", "Event-Rules"), ("الفعاليات", "Events"), ("المزاد", "Auction")], []),
    ("كرة القدم", "FOOTBALL", "✪",
     [("أخبار-الكرة", "Football-News"), ("دردشة-الكرة", "Football-Chat"),
      ("توقعات-المباريات", "Predictions")], []),
    (SUPPORT_CATEGORY, "SUPPORT", "☥",
     [("التذكرة", "Ticket")], [("الدعم الفني", "Tech-Support")]),
    ("غرف الفرق", "TEAM-VOICE", "☯", [],
     [("الفريق الأول", "Team-One"), ("الفريق الثاني", "Team-Two"), ("الفريق الثالث", "Team-Three"),
      ("الفريق الرابع", "Team-Four")]),
    ("البطولات", "TOURNAMENTS", "⚔",
     [("البطولة", "Tournament"), ("تسجيل-البطولة", "Registration")], []),
    # ── 5 أقسام جديدة من عندي (الألعاب = قسم لكل لعبة) ──
    ("الألعاب", "GAMES", "♆",
     [("اختيار-الرتب", "Roles"), ("ألعاب-أخرى", "Other-Games")], []),
    ("روبلوكس", "ROBLOX", "⚡",
     [("شات-روبلوكس", "Roblox-Chat"), ("قوانين-روبلوكس", "Roblox-Rules"),
      ("سكربتات-روبلوكس", "Roblox-Scripts"), ("هاكات-روبلوكس", "Roblox-Hacks")],
     [("غرفة روبلوكس", "Roblox-Voice")]),
    ("ماينكرافت", "MINECRAFT", "☘",
     [("شات-ماينكرافت", "Minecraft-Chat"), ("قوانين-ماينكرافت", "Minecraft-Rules"),
      ("سيرفرات-ماينكرافت", "Minecraft-Servers")],
     [("غرفة ماينكرافت", "Minecraft-Voice")]),
    ("ببجي موبايل", "PUBG-MOBILE", "☠",
     [("شات-ببجي", "PUBG-Chat"), ("قوانين-ببجي", "PUBG-Rules"), ("ملفات-ببجي", "PUBG-Files"),
      ("فريق-ببجي", "PUBG-Team")],
     [("غرفة ببجي", "PUBG-Voice"), ("تيم ببجي الأول", "PUBG-Team-One"),
      ("تيم ببجي الثاني", "PUBG-Team-Two")]),
    ("امونج اس", "AMONG-US", "☢",
     [("شات-امونج-اس", "Among-Chat"), ("قوانين-امونج-اس", "Among-Rules"),
      ("كود-امونج-اس", "Among-Codes")],
     [("غرفة امونج الأولى", "Among-One"), ("غرفة امونج الثانية", "Among-Two"),
      ("غرفة امونج الثالثة", "Among-Three")]),
    ("بيس", "PES", "⚽",
     [("شات-بيس", "PES-Chat"), ("قوانين-بيس", "PES-Rules")],
     [("غرفة بيس", "PES-Voice")]),
    ("كول اوف ديوتي", "CALL-OF-DUTY", "✈",
     [("شات-كول-اوف-ديوتي", "COD-Chat"), ("قوانين-كول-اوف-ديوتي", "COD-Rules")],
     [("غرفة كول الأولى", "COD-One"), ("غرفة كول الثانية", "COD-Two")]),
    ("كلاش اوف كلانس", "CLASH-OF-CLANS", "♞",
     [("شات-كلاش-اوف-كلانس", "Clash-Chat"), ("قوانين-كلاش-اوف-كلانس", "Clash-Rules"),
      ("بحث-عن-كلان", "Clan-Search")],
     [("غرفة كلاش الأولى", "Clash-One"), ("غرفة كلاش الثانية", "Clash-Two")]),
    ("فري فاير", "FREE-FIRE", "☄",
     [("شات-فري-فاير", "FF-Chat"), ("قوانين-فري-فاير", "FF-Rules"),
      ("بحث-عن-فريق-فري-فاير", "FF-LFG")],
     [("غرفة فري فاير الأولى", "FF-One"), ("غرفة فري فاير الثانية", "FF-Two")]),
    ("جتا 5", "GTA-V", "♠",
     [("شات-جتا", "GTA-Chat"), ("قوانين-جتا", "GTA-Rules"), ("سيرفرات-فايف-ام", "FiveM-Servers")],
     [("غرفة جتا الأولى", "GTA-One"), ("غرفة جتا الثانية", "GTA-Two")]),
    ("سهرات", "NIGHTS", "♥",
     [("شات-السهرات", "Nights-Chat"), ("شات-الشطرنج", "Chess-Chat"), ("شات-اونو", "Uno-Chat"),
      ("شات-الشدة", "Cards-Chat")],
     [("غرفة الشدة الأولى", "Cards-One"), ("غرفة الشدة الثانية", "Cards-Two"),
      ("غرفة اونو", "Uno-Voice"), ("غرفة الشطرنج", "Chess-Voice"), ("غرفة السهرة", "Nights-Voice")]),
    ("الاقتصاد", "ECONOMY", "❖",
     [("المتجر", "Shop"), ("المكافأة-اليومية", "Daily"), ("الأرصدة", "Balance"),
      ("ألعاب-مصغرة", "Mini-Games"), ("المسابقات", "Trivia")], []),
    ("صناعة المحتوى", "CREATORS", "✧",
     [("الفيديوهات", "Videos"), ("البث-المباشر", "Live"), ("تصاميم-الأعضاء", "Designs"),
      ("لقطات", "Clips"), ("ترويج-الحسابات", "Promo")], []),
    ("التقديم", "APPLY", "✦",
     [("شروط-التقديم", "Requirements"), ("تقديم-الإدارة", "Apply"), ("نتائج-التقديم", "Results")], []),
    (ADMIN_CATEGORY, "STAFF", "✠",
     [("السجل", "Logs"), ("نقاش-الإدارة", "Staff-Chat"), ("مراجعة-التقديمات", "Review-Apps"),
      ("طلبات-الدعم", "Support-Staff"), ("قرارات-الإدارة", "Decisions")],
     [("اجتماع الإدارة", "Staff-Voice")]),
]

LAYOUT, CAT_STYLE, CH_STYLE = {}, {}, {}
for _cat, _en, _sym, _texts, _voices in SPEC:
    LAYOUT[_cat] = {"text": [a for a, _ in _texts], "voice": [a for a, _ in _voices]}
    CAT_STYLE[_cat] = (_en, _sym)
    for _ar, _e in _texts + _voices:
        CH_STYLE[_ar] = _e

READ_ONLY = {"الترحيب", "القوانين", "الأخبار", "المتصدرون", "التذكرة", "قوانين-الفعاليات",
             "أخبار-الكرة", "اختيار-الرتب", "شروط-التقديم", "نتائج-التقديم",
             "قوانين-روبلوكس", "قوانين-ماينكرافت", "قوانين-ببجي", "قوانين-امونج-اس", "قوانين-بيس",
             "قوانين-كول-اوف-ديوتي", "قوانين-كلاش-اوف-كلانس", "قوانين-فري-فاير", "قوانين-جتا", "المستوى"}
PRIVATE_CATEGORIES = {ADMIN_CATEGORY}


def bold(text: str) -> str:
    """Rules -> 𝐑𝐮𝐥𝐞𝐬"""
    out = []
    for c in text:
        if "A" <= c <= "Z":
            out.append(chr(0x1D400 + ord(c) - 65))
        elif "a" <= c <= "z":
            out.append(chr(0x1D41A + ord(c) - 97))
        else:
            out.append(c)
    return "".join(out)


def key(name: str) -> str:
    """يترك العربي فقط ويوحّد الهمزات، فالمطابقة تنجح مع الاسم القديم والمزخرف"""
    name = re.sub(r"[^\u0600-\u06FF \-]", "", name)
    name = re.sub("[أإآ]", "ا", name)
    name = re.sub("[\u064B-\u0652]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip(" -")


def _find(items, name: str):
    k = key(name)
    if not k:
        return discord.utils.get(items, name=name)
    return next((c for c in items if key(c.name) == k), None)


def find_text(guild: discord.Guild, name: str):
    return _find(guild.text_channels, name)


def find_voice(guild: discord.Guild, name: str):
    return _find(guild.voice_channels, name)


def find_category(guild: discord.Guild, name: str):
    return _find(guild.categories, name)


def styled_category(name: str) -> str:
    en, sym = CAT_STYLE.get(name, (None, None))
    return f"{bold(en)} • {sym} • {name}" if en else name


def styled_channel(cat: str, name: str) -> str:
    sym = CAT_STYLE.get(cat, (None, "✦"))[1]
    en = CH_STYLE.get(name)
    ar = re.sub(r"^[^\u0600-\u06FF]+", "", name)  # يشيل الإيموجي من أول الاسم
    return f"{sym}・{bold(en)}・{ar}" if en else name


# ألوان
PRIMARY = discord.Colour.from_rgb(88, 101, 242)
GOLD = discord.Colour.from_rgb(255, 193, 7)
GREEN = discord.Colour.from_rgb(46, 204, 113)
RED = discord.Colour.from_rgb(231, 76, 60)
ORANGE = discord.Colour.from_rgb(243, 156, 18)

LINE = "━━━━━━━━━━━━━━━━━━"


# ============================================================
#                     حفظ البيانات
# ============================================================
def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    for key, default in (("panels", {}), ("meme_clips", []), ("users", {}), ("autoposts", []),
                         ("giveaways", {}),
                         ("badwords", {}), ("tempvoice", []), ("config", {})):
        data.setdefault(key, default)
    return data


def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(DATA, f, ensure_ascii=False)


DATA = load_data()
last_xp = {}
spam_tracker = {}
URL_RE = re.compile(r"(https?://|www\.|discord\.gg/|discord\.com/invite/)", re.I)

intents = discord.Intents.default()
intents.members = True          # Server Members Intent
intents.message_content = True  # Message Content Intent (للحماية التلقائية)
bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents, help_command=None)


# ============================================================
#                     دوال مساعدة
# ============================================================
def cfg(guild: discord.Guild, key: str) -> str:
    return DATA["config"].get(str(guild.id), {}).get(key, DEFAULT_CONFIG[key])


def make_embed(title: str, desc: Optional[str] = None, colour: discord.Colour = PRIMARY,
               thumb: Optional[str] = None) -> discord.Embed:
    embed = discord.Embed(title=title, description=desc, colour=colour,
                          timestamp=discord.utils.utcnow())
    embed.set_footer(text=f"✦ {BRAND} ✦")
    if thumb:
        embed.set_thumbnail(url=thumb)
    return embed


async def send_log(guild: discord.Guild, embed: discord.Embed, file: Optional[discord.File] = None):
    channel = find_text(guild, cfg(guild, "log_channel"))
    if channel:
        try:
            await channel.send(embed=embed, file=file)
        except discord.HTTPException:
            pass


LFG_CHANNELS = {"🎮 ماينكرافت": "شات-ماينكرافت", "🔫 ببجي": "فريق-ببجي", "🕹 ألعاب أخرى": "ألعاب-أخرى"}


async def in_home(interaction: discord.Interaction, key: str, name: Optional[str] = None) -> bool:
    """يتأكد إن الأمر مستخدم بالروم المخصص له، وإلا بيوجّه العضو له. الأدمن بيستخدمه بأي مكان"""
    guild = interaction.guild
    home = find_text(guild, name or cfg(guild, key))
    if home is None or home.id == interaction.channel_id:
        return True
    if interaction.user.guild_permissions.administrator:
        return True
    await interaction.response.send_message(f"📍 هالأمر مخصص لـ {home.mention}", ephemeral=True)
    return False


def get_user(guild_id: int, user_id: int) -> dict:
    return DATA["users"].setdefault(f"{guild_id}:{user_id}", {"xp": 0})


def level_from_xp(xp: int) -> int:
    return int(math.sqrt(xp / 50))


def xp_for_level(level: int) -> int:
    return 50 * level * level


def add_xp(guild_id: int, user_id: int, amount: int):
    user = get_user(guild_id, user_id)
    old = level_from_xp(user["xp"])
    user["xp"] += amount
    new = level_from_xp(user["xp"])
    save_data()
    return old, new, user["xp"]


def add_coins(guild_id: int, user_id: int, amount: int) -> int:
    user = get_user(guild_id, user_id)
    user["coins"] = user.get("coins", 0) + amount
    save_data()
    return user["coins"]


async def check_level_roles(member: discord.Member, level: int):
    for lvl, name in LEVEL_ROLES.items():
        if level >= lvl:
            role = discord.utils.get(member.guild.roles, name=name)
            if role and role not in member.roles:
                try:
                    await member.add_roles(role)
                except discord.Forbidden:
                    pass


def guild_posts(guild_id: int):
    return [p for p in DATA["autoposts"] if p["guild_id"] == guild_id]


# ============================================================
#                  أزرار اختيار الرتب
# ============================================================
class RoleButton(discord.ui.Button):
    def __init__(self, role_name: str):
        super().__init__(label=role_name, style=discord.ButtonStyle.primary,
                         custom_id=f"role:{role_name}")
        self.role_name = role_name

    async def callback(self, interaction: discord.Interaction):
        role = discord.utils.get(interaction.guild.roles, name=self.role_name)
        if role is None:
            return await interaction.response.send_message(
                "الرتبة غير موجودة، شغّل /setup_server أولاً.", ephemeral=True)
        member = interaction.user
        try:
            if role in member.roles:
                await member.remove_roles(role)
                msg = f"✅ تم إزالة رتبة {role.name}"
            else:
                await member.add_roles(role)
                msg = f"✅ تم إعطاؤك رتبة {role.name}"
        except discord.Forbidden:
            msg = "❌ ما عندي صلاحية. ارفع رتبة البوت فوق رتب الألعاب."
        await interaction.response.send_message(msg, ephemeral=True)


class RolesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for r in GAME_ROLES:
            self.add_item(RoleButton(r))


# ============================================================
#                   نظام التذاكر
# ============================================================
TICKET_TYPES = {
    "support": ("🛠", "دعم-فني"),
    "complaint": ("📣", "شكوى"),
    "suggestion": ("💡", "اقتراح"),
}


async def build_transcript(channel: discord.TextChannel) -> str:
    lines = []
    async for m in channel.history(limit=500, oldest_first=True):
        stamp = m.created_at.strftime("%Y-%m-%d %H:%M")
        content = m.content or ("[مرفق أو إيمبد]" if (m.attachments or m.embeds) else "")
        lines.append(f"[{stamp}] {m.author.display_name}: {content}")
    return "\n".join(lines)


class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 إغلاق التذكرة", style=discord.ButtonStyle.danger,
                       custom_id="ticket:close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        is_owner = channel.topic == f"ticket:{interaction.user.id}"
        is_staff = interaction.user.guild_permissions.manage_channels
        if not (is_owner or is_staff):
            return await interaction.response.send_message("❌ ما تقدر تغلق هذي التذكرة.", ephemeral=True)
        await interaction.response.send_message("🔒 جاري حفظ المحادثة وإغلاق التذكرة...")
        transcript = await build_transcript(channel)
        file = discord.File(io.BytesIO(transcript.encode("utf-8")), filename=f"{channel.name}.txt")
        embed = make_embed("🎫 تذكرة مغلقة",
                           f"**الروم:** {channel.name}\n**أغلقها:** {interaction.user.mention}", RED)
        await send_log(interaction.guild, embed, file)
        await asyncio.sleep(3)
        await channel.delete()


class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=name.replace("-", " "), value=key, emoji=emoji)
                   for key, (emoji, name) in TICKET_TYPES.items()]
        super().__init__(placeholder="🎫 اختر نوع التذكرة...", options=options,
                         custom_id="ticket:type")

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user
        emoji, name = TICKET_TYPES[self.values[0]]
        for ch in guild.text_channels:
            if ch.topic == f"ticket:{user.id}":
                return await interaction.response.send_message(
                    f"عندك تذكرة مفتوحة: {ch.mention}", ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        mod = discord.utils.get(guild.roles, name=MOD_ROLE)
        if mod:
            overwrites[mod] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        category = find_category(guild, SUPPORT_CATEGORY)

        channel = await guild.create_text_channel(
            f"{name}-{user.name}", overwrites=overwrites, category=category,
            topic=f"ticket:{user.id}")
        embed = make_embed(f"{emoji} تذكرة {name.replace('-', ' ')}",
                           f"## أهلاً {user.display_name}\nاشرح موضوعك بالتفصيل وراح يرد عليك المشرفون قريباً.",
                           GREEN)
        await channel.send(content=user.mention, embed=embed, view=CloseView())
        staff = find_text(guild, cfg(guild, "staff_tickets_channel"))
        if staff:
            try:
                await staff.send(embed=make_embed(
                    "🎫 تذكرة جديدة", f"{user.mention} فتح {channel.mention}\nالنوع: {name.replace('-', ' ')}", GOLD))
            except discord.HTTPException:
                pass
        await interaction.response.send_message(f"✅ تم فتح تذكرتك: {channel.mention}", ephemeral=True)
        try:
            await interaction.message.edit(view=TicketView())  # يرجع القائمة لوضعها الأول
        except discord.HTTPException:
            pass


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# ============================================================
#              تسجيل لاعبين (LFG والبطولات)
# ============================================================
class SignupView(discord.ui.View):
    def __init__(self, owner: discord.abc.User, title: str, note: str, slots: int,
                 owner_joins: bool = True, colour: discord.Colour = PRIMARY):
        super().__init__(timeout=7200)
        self.title = title
        self.note = note
        self.slots = slots
        self.colour = colour
        self.players = [owner.id] if owner_joins else []

    def render(self) -> discord.Embed:
        names = "\n".join(f"`{i}.` <@{uid}>" for i, uid in enumerate(self.players, 1))
        if not names:
            names = "— لا أحد بعد —"
        desc = f"{self.note}\n{LINE}\n**اللاعبون ({len(self.players)}/{self.slots})**\n{names}"
        return make_embed(self.title, desc, self.colour)

    @discord.ui.button(label="✅ انضم", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        if uid in self.players:
            return await interaction.response.send_message("أنت مسجل أصلاً ✅", ephemeral=True)
        if len(self.players) >= self.slots:
            return await interaction.response.send_message("😕 العدد اكتمل.", ephemeral=True)
        self.players.append(uid)
        full = len(self.players) >= self.slots
        if full:
            button.disabled = True
        await interaction.response.edit_message(embed=self.render(), view=self)
        if full:
            mentions = " ".join(f"<@{p}>" for p in self.players)
            await interaction.channel.send(f"🎮 اكتمل العدد! جاهزين؟ {mentions}")

    @discord.ui.button(label="🚪 انسحب", style=discord.ButtonStyle.danger)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        if uid not in self.players:
            return await interaction.response.send_message("أنت مو مسجل.", ephemeral=True)
        self.players.remove(uid)
        self.children[0].disabled = False
        await interaction.response.edit_message(embed=self.render(), view=self)


# ============================================================
#                       الهدايا
# ============================================================
class GiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎉 شارك", style=discord.ButtonStyle.success, custom_id="giveaway:join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = DATA["giveaways"].get(str(interaction.message.id))
        if not g or g["ended"]:
            return await interaction.response.send_message("انتهت هذي الفعالية.", ephemeral=True)
        uid = interaction.user.id
        if uid in g["entries"]:
            g["entries"].remove(uid)
            msg = "🚪 تم سحب مشاركتك"
        else:
            g["entries"].append(uid)
            msg = "✅ تم تسجيل مشاركتك، بالتوفيق!"
        save_data()
        await interaction.response.send_message(f"{msg} ({len(g['entries'])} مشارك)", ephemeral=True)


async def end_giveaway(message_id: str, g: dict):
    g["ended"] = True
    save_data()
    channel = bot.get_channel(g["channel_id"])
    if not channel:
        return
    try:
        message = await channel.fetch_message(int(message_id))
    except discord.HTTPException:
        message = None
    entries = g["entries"]
    winners = random.sample(entries, min(g["winners"], len(entries)))
    text = " ".join(f"<@{w}>" for w in winners) if winners else "لا يوجد مشاركون 😢"
    embed = make_embed("🎁 انتهت الفعالية", f"## {g['prize']}\n{LINE}\n**الفائزون:** {text}", GOLD)
    if message:
        try:
            await message.edit(embed=embed, view=None)
        except discord.HTTPException:
            pass
    if winners:
        await channel.send(f"🎊 مبروك {text}! ربحت **{g['prize']}**")


# ============================================================
#                      ألعاب صغيرة
# ============================================================
CHOICES = {"rock": "🪨 حجر", "paper": "📄 ورقة", "scissors": "✂️ مقص"}
BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}


class RPSView(discord.ui.View):
    def __init__(self, player: discord.abc.User):
        super().__init__(timeout=30)
        self.player = player

    async def play(self, interaction: discord.Interaction, choice: str):
        if interaction.user.id != self.player.id:
            return await interaction.response.send_message("هذي مو لعبتك، اكتب /rps", ephemeral=True)
        bot_choice = random.choice(list(CHOICES))
        if choice == bot_choice:
            result, colour = "🤝 تعادل!", ORANGE
        elif BEATS[choice] == bot_choice:
            result, colour = "🎉 فزت!", GREEN
        else:
            result, colour = "😅 خسرت!", RED
        for c in self.children:
            c.disabled = True
        embed = make_embed("✊ حجر ورقة مقص",
                           f"أنت: {CHOICES[choice]}\nالبوت: {CHOICES[bot_choice]}\n{LINE}\n## {result}", colour)
        await interaction.response.edit_message(content=None, embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="🪨 حجر", style=discord.ButtonStyle.secondary)
    async def rock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play(interaction, "rock")

    @discord.ui.button(label="📄 ورقة", style=discord.ButtonStyle.secondary)
    async def paper(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play(interaction, "paper")

    @discord.ui.button(label="✂️ مقص", style=discord.ButtonStyle.secondary)
    async def scissors(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play(interaction, "scissors")


QUESTIONS = [
    {"q": "ما المادة اللازمة لصنع بوابة النذر (Nether) في ماينكرافت؟",
     "o": ["أوبسيديان", "حجر عادي", "ذهب", "ألماس"], "a": 0},
    {"q": "ما اسم المخلوق الأخضر الذي ينفجر في ماينكرافت؟",
     "o": ["كريبر", "زومبي", "سكيلتون", "إندرمان"], "a": 0},
    {"q": "كم عدد اللاعبين في فريق سكواد (Squad) في ببجي موبايل؟",
     "o": ["2", "4", "6", "8"], "a": 1},
    {"q": "من هي الشركة المطورة لسلسلة ماريو؟",
     "o": ["نينتندو", "سوني", "مايكروسوفت", "سيغا"], "a": 0},
    {"q": "كم عدد قلوب الصحة الكاملة للاعب في ماينكرافت؟",
     "o": ["5", "10", "20", "3"], "a": 1},
    {"q": "ما اسم التنين الموجود في بُعد الإند (End) في ماينكرافت؟",
     "o": ["إندر دراغون", "واردن", "غاست", "ويذر"], "a": 0},
]


class TriviaView(discord.ui.View):
    def __init__(self, player: discord.abc.User, question: dict):
        super().__init__(timeout=40)
        self.player = player
        self.question = question
        for i, opt in enumerate(question["o"]):
            button = discord.ui.Button(label=opt, style=discord.ButtonStyle.secondary)
            button.callback = self.make_callback(i)
            self.add_item(button)

    def make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.player.id:
                return await interaction.response.send_message(
                    "هذا السؤال مو لك، اكتب /trivia", ephemeral=True)
            for c in self.children:
                c.disabled = True
            q = self.question
            if index == q["a"]:
                old, new, _ = add_xp(interaction.guild.id, interaction.user.id, 30)
                add_coins(interaction.guild.id, interaction.user.id, 10)
                result = "## ✅ إجابة صحيحة!\n+30 نقطة و +10 عملات"
                colour = GREEN
                if new > old:
                    add_coins(interaction.guild.id, interaction.user.id, 50)
                    await check_level_roles(interaction.user, new)
                    await announce_level(interaction.guild, interaction.user, new, interaction.channel)
            else:
                result = f"## ❌ إجابة خاطئة\nالصحيح: **{q['o'][q['a']]}**"
                colour = RED
            embed = make_embed("🧠 سؤال", f"**{q['q']}**\n{LINE}\n{result}", colour)
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
        return callback


# ============================================================
#                        الأحداث
# ============================================================
# ============================================================
#                  بطاقة الترحيب بالصورة
# ============================================================
ARABIC_FONT_PATHS = [
    "font.ttf",  # ضع هنا أي خط عربي تحبه بجانب البوت
    "/system/fonts/NotoNaskhArabic-Regular.ttf",
    "/system/fonts/NotoSansArabic-Regular.ttf",
    "/system/fonts/NotoKufiArabic-Regular.ttf",
    "/system/fonts/DroidSansArabic.ttf",
]
LATIN_FONT_PATHS = ["/system/fonts/Roboto-Regular.ttf", "/system/fonts/DroidSans.ttf"]


def clean_name(name: str) -> str:
    """يحوّل الحروف المزخرفة لعادية ويشيل الإيموجي والرموز اللي الخط ما بيرسمها"""
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"[^\w\s\u0600-\u06FF\-\.]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "Member"


def has_arabic(text: str) -> bool:
    return any("\u0600" <= c <= "\u06FF" for c in text)


def find_arabic_font() -> Optional[str]:
    for path in ARABIC_FONT_PATHS:
        if os.path.exists(path):
            return path
    found = glob.glob("/system/fonts/*Arabic*")
    return found[0] if found else None


ARABIC_FONT = find_arabic_font()
ARABIC_OK = bool(PIL_OK and ARABIC_FONT and (RAQM or RESHAPE_OK))


def load_font(size: int, arabic: bool = False):
    paths = [ARABIC_FONT] if (arabic and ARABIC_FONT) else LATIN_FONT_PATHS
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def shape(text: str) -> str:
    # إذا Pillow فيه raqm فهو يشكّل العربي ويرتبه لوحده، وإعادة الترتيب تعكس الكلام
    if RAQM:
        return text
    if ARABIC_OK and has_arabic(text):
        return get_display(arabic_reshaper.reshape(text))
    return text


def build_welcome_card(avatar_bytes: bytes, name: str, number: int) -> io.BytesIO:
    """بطاقة ترحيب بثيم النار: لهب وشرر وحلقة نارية حول الصورة"""
    W, H = 900, 480
    rnd = random.Random(number)  # كل عضو ياخذ لهب مختلف شوي

    def lerp(c1, c2, t):
        return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

    # ── الخلفية: أسود يميل للأحمر الغامق ──
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(10 + 46 * t ** 2), int(5 + 8 * t ** 2), int(9 + 5 * t)))

    # ── توهج أحمر خلف الصورة ──
    cx, cy = W // 2, 148
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse((cx - 150, cy - 150, cx + 150, cy + 150), fill=(255, 60, 0))
    img = ImageChops.add(img, glow.filter(ImageFilter.GaussianBlur(60)).point(lambda v: int(v * 0.55)))

    # ── ألسنة اللهب (ثلاث طبقات: أحمر، برتقالي، أصفر) ──
    def flames(color, count, hmin, hmax, wmin, wmax, blur):
        layer = Image.new("RGB", (W, H), (0, 0, 0))
        ld = ImageDraw.Draw(layer)
        for _ in range(count):
            fx = rnd.uniform(-30, W + 30)
            edge = abs(fx - W / 2) / (W / 2)           # 0 بالنص ... 1 عالأطراف
            h = rnd.uniform(hmin, hmax) * (0.32 + 0.9 * edge)
            w = rnd.uniform(wmin, wmax)
            lean = rnd.uniform(-0.7, 0.7) * w
            left, right = [], []
            for i in range(19):
                t = i / 18
                half = w * (1 - t) ** 0.75 * (1 + 0.25 * math.sin(math.pi * t))
                x = fx + lean * t * t + math.sin(t * 5 + fx) * w * 0.08
                y = H - t * h
                left.append((x - half, y))
                right.append((x + half, y))
            ld.polygon(left + right[::-1], fill=color)
        return layer.filter(ImageFilter.GaussianBlur(blur))

    img = ImageChops.screen(img, flames((150, 14, 0), 42, 170, 320, 46, 92, 10))
    img = ImageChops.screen(img, flames((255, 88, 0), 46, 120, 250, 30, 62, 6))
    img = ImageChops.screen(img, flames((255, 150, 25), 52, 60, 150, 16, 38, 3))

    # ── تعتيم ناعم خلف النصوص عشان تنقرا بسهولة ──
    shade = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shade).rounded_rectangle((120, 235, W - 120, 445), radius=60, fill=255)
    shade = shade.filter(ImageFilter.GaussianBlur(38)).point(lambda v: int(v * 0.62))
    img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, shade)

    # ── شرر طاير ──
    sparks = Image.new("RGB", (W, H), (0, 0, 0))
    sd = ImageDraw.Draw(sparks)
    for _ in range(70):
        sx = rnd.uniform(0, W)
        sy = H - abs(rnd.gauss(0, 170))
        r = rnd.choice((1, 1, 2, 2, 3))
        sd.ellipse((sx - r, sy - r, sx + r, sy + r), fill=rnd.choice(((255, 220, 90), (255, 150, 30), (255, 90, 20))))
    img = ImageChops.add(img, sparks.filter(ImageFilter.GaussianBlur(1)))
    img = ImageChops.add(img, sparks.filter(ImageFilter.GaussianBlur(5)))
    d = ImageDraw.Draw(img)

    # ── إطار ناري بتوهج ──
    frame_glow = Image.new("RGB", (W, H), (0, 0, 0))
    ImageDraw.Draw(frame_glow).rounded_rectangle([14, 14, W - 14, H - 14], radius=28,
                                                 outline=(255, 90, 0), width=6)
    img = ImageChops.add(img, frame_glow.filter(ImageFilter.GaussianBlur(7)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([14, 14, W - 14, H - 14], radius=28, outline=(255, 150, 20), width=3)
    d.rounded_rectangle([25, 25, W - 25, H - 25], radius=21, outline=(120, 40, 10), width=1)

    # ── خطوط زخرفية على جانبي الصورة ──
    def diamond(x, y, r, fill):
        d.polygon([(x, y - r), (x + r, y), (x, y + r), (x - r, y)], fill=fill)

    for side in (-1, 1):
        far, near = cx + side * 385, cx + side * 135
        d.line([(far, cy), (near, cy)], fill=(255, 140, 20), width=2)
        diamond(far, cy, 8, (255, 120, 10))
        diamond(near, cy, 5, (255, 225, 120))

    # ── الصورة بحلقة نار متدرجة ──
    size = 156
    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGB").resize((size, size), Image.LANCZOS)
    big = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(big).ellipse((0, 0, size * 4, size * 4), fill=255)
    mask = big.resize((size, size), Image.LANCZOS)
    outer = size + 28
    for i in range(10):
        dia = outer - 2 * i
        col = lerp((255, 35, 0), (255, 215, 60), i / 9)
        d.ellipse((cx - dia // 2, cy - dia // 2, cx + dia // 2, cy + dia // 2), fill=col)
    dark = size + 8
    d.ellipse((cx - dark // 2, cy - dark // 2, cx + dark // 2, cy + dark // 2), fill=(16, 7, 7))
    img.paste(avatar, (cx - size // 2, cy - size // 2), mask)

    # ── نص بتدرج ناري وتوهج ──
    def fire_text(canvas, text, font, y, c_top, c_bottom, glow_col):
        dd = ImageDraw.Draw(canvas)
        box = dd.textbbox((0, 0), text, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        x = (W - tw) // 2 - box[0]
        g = Image.new("RGB", (W, H), (0, 0, 0))
        ImageDraw.Draw(g).text((x, y), text, font=font, fill=glow_col)
        canvas = ImageChops.add(canvas, g.filter(ImageFilter.GaussianBlur(9)))
        ImageDraw.Draw(canvas).text((x, y), text, font=font, fill=(20, 4, 0),
                                    stroke_width=4, stroke_fill=(20, 4, 0))
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).text((x, y), text, font=font, fill=255)
        grad = Image.new("RGB", (W, H))
        gd = ImageDraw.Draw(grad)
        top_y, bot_y = y + box[1], y + box[3]
        for row in range(max(0, top_y - 2), min(H, bot_y + 3)):
            t = min(1, max(0, (row - top_y) / max(1, bot_y - top_y)))
            gd.line([(0, row), (W, row)], fill=lerp(c_top, c_bottom, t))
        canvas.paste(grad, (0, 0), m)
        return canvas, tw, th, box

    shown = clean_name(name)[:22]
    if has_arabic(shown) and not ARABIC_OK:
        shown = "NEW MEMBER"
    title = "أهلاً بك في السيرفر" if ARABIC_OK else "WELCOME"
    sub = f"أنت العضو رقم {number}" if ARABIC_OK else f"Member #{number}"

    img, *_ = fire_text(img, shape(title), load_font(44, ARABIC_OK), 250,
                        (255, 238, 140), (255, 120, 10), (255, 70, 0))

    name_arabic = ARABIC_OK and has_arabic(shown)
    fsize = 46
    font = load_font(fsize, name_arabic)
    while fsize > 24 and d.textlength(shape(shown), font=font) > W - 160:
        fsize -= 3
        font = load_font(fsize, name_arabic)
    img, *_ = fire_text(img, shape(shown), font, 306, (255, 255, 255), (255, 214, 150), (255, 110, 20))

    # ── شارة رقم العضو ──
    sub_font = load_font(26, ARABIC_OK)
    text = shape(sub)
    box = ImageDraw.Draw(img).textbbox((0, 0), text, font=sub_font)
    tw, th = box[2] - box[0], box[3] - box[1]
    px, py, y0 = 34, 12, 378
    x0, x1 = (W - tw) // 2 - px, (W + tw) // 2 + px
    pg = Image.new("RGB", (W, H), (0, 0, 0))
    ImageDraw.Draw(pg).rounded_rectangle([x0, y0, x1, y0 + th + 2 * py], radius=26, outline=(255, 90, 0), width=5)
    img = ImageChops.add(img, pg.filter(ImageFilter.GaussianBlur(6)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0, y0, x1, y0 + th + 2 * py], radius=26, fill=(26, 8, 6), outline=(255, 150, 20), width=3)
    img, *_ = fire_text(img, text, sub_font, y0 + py - box[1] - 1, (255, 245, 170), (255, 150, 20), (255, 90, 0))

    # ── اسم السيرفر بالأعلى ──
    d = ImageDraw.Draw(img)
    brand_font = load_font(17)
    brand = "  ".join(BRAND)
    bb = d.textbbox((0, 0), brand, font=brand_font)
    d.text(((W - (bb[2] - bb[0])) // 2 - bb[0], 30), brand, font=brand_font, fill=(255, 175, 70))

    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


async def build_welcome(member: discord.Member):
    guild = member.guild
    file = None
    if PIL_OK:
        try:
            avatar_bytes = await member.display_avatar.replace(size=256, format="png").read()
            buf = await asyncio.to_thread(build_welcome_card, avatar_bytes,
                                          member.display_name, guild.member_count)
            file = discord.File(buf, filename="welcome.png")
        except Exception as error:
            print(f"[WARN] welcome card failed: {error}")

    def mention(name: str) -> str:
        ch = find_text(guild, name)
        return ch.mention if ch else f"#{name}"

    desc = (f"## أهلاً {member.mention} 👋\n"
            f"نورتنا في **{guild.name}**\n{LINE}\n"
            f"أنت العضو رقم **{guild.member_count}**\n"
            f"📜 اقرأ {mention('القوانين')}\n"
            f"🎮 اختر لعبتك من {mention('اختيار-الرتب')}\n"
            f"🎫 تحتاج مساعدة؟ {mention('التذكرة')}")
    embed = make_embed("🔥 عضو جديد", desc, discord.Colour.from_rgb(255, 90, 0),
                       thumb=None if file else member.display_avatar.url)
    if file:
        embed.set_image(url="attachment://welcome.png")
    return embed, file


async def setup_hook():
    bot.add_view(RolesView())
    bot.add_view(TicketView())
    bot.add_view(CloseView())
    bot.add_view(GiveawayView())
    bot.add_view(ShopView())
    bot.add_view(DailyView())
    bot.add_view(BankView())
    background_loop.start()
    web_loop.start()
    for loop in (bank_loop, meme_loop, dhikr_loop):
        if not loop.is_running():
            loop.start()

bot.setup_hook = setup_hook


@bot.event
async def on_ready():
    for guild in bot.guilds:
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
    print(f"[OK] Bot is online: {bot.user} | version {BOT_VERSION}")


@bot.event
async def on_guild_join(guild: discord.Guild):
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)


@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    role = discord.utils.get(guild.roles, name=MEMBER_ROLE)
    if role:
        try:
            await member.add_roles(role)
        except discord.Forbidden:
            pass

    channel = find_text(guild, cfg(guild, "welcome_channel"))
    if channel:
        embed, file = await build_welcome(member)
        await channel.send(content=member.mention, embed=embed, file=file)

    # تنبيه الحسابات الجديدة
    age_days = (discord.utils.utcnow() - member.created_at).days
    try:
        limit = int(cfg(guild, "new_account_days"))
    except ValueError:
        limit = 3
    if age_days < limit:
        embed = make_embed("⚠️ حساب جديد جداً",
                           f"{member.mention} عمر حسابه **{age_days}** يوم فقط.", ORANGE,
                           thumb=member.display_avatar.url)
        await send_log(guild, embed)


@bot.event
async def on_member_remove(member: discord.Member):
    embed = make_embed("👋 غادر السيرفر", f"{member} (`{member.id}`)", RED)
    await send_log(member.guild, embed)


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState,
                                after: discord.VoiceState):
    # إنشاء غرفة مؤقتة
    if after.channel and key(after.channel.name) == key(CREATOR_VC):
        overwrites = {member: discord.PermissionOverwrite(manage_channels=True, move_members=True)}
        try:
            vc = await member.guild.create_voice_channel(
                f"🎧 غرفة {member.display_name}", category=after.channel.category,
                overwrites=overwrites)
            DATA["tempvoice"].append(vc.id)
            save_data()
            await member.move_to(vc)
        except discord.HTTPException:
            pass
    # حذف الغرفة المؤقتة الفاضية
    if before.channel and before.channel.id in DATA["tempvoice"] and not before.channel.members:
        try:
            await before.channel.delete()
        except discord.HTTPException:
            pass
        DATA["tempvoice"].remove(before.channel.id)
        save_data()


# ============================================================
#                  الحماية التلقائية
# ============================================================
async def run_automod(message: discord.Message) -> bool:
    guild = message.guild
    content = message.content or ""
    now = time.time()
    key = (guild.id, message.author.id)
    times = [t for t in spam_tracker.get(key, []) if now - t < 6]
    times.append(now)
    spam_tracker[key] = times

    reason = None
    is_spam = False
    channel_name = getattr(message.channel, "name", "")
    if key(channel_name) not in {key(n) for n in LINK_CHANNELS} and URL_RE.search(content):
        reason = "الروابط غير مسموحة هنا"
    elif any(w in content.lower() for w in DATA["badwords"].get(str(guild.id), [])):
        reason = "كلمة ممنوعة"
    elif len(times) >= 6:
        reason = "سبام: رسائل كثيرة بسرعة"
        is_spam = True
    if not reason:
        return False

    try:
        await message.delete()
    except discord.HTTPException:
        pass
    await message.channel.send(f"🚫 {message.author.mention} {reason}", delete_after=6)
    if is_spam:
        spam_tracker[key] = []
        try:
            await message.author.timeout(datetime.timedelta(minutes=5), reason="سبام")
        except discord.HTTPException:
            pass
    embed = make_embed("🛡 حماية تلقائية",
                       f"**العضو:** {message.author.mention}\n**الروم:** {message.channel.mention}\n"
                       f"**السبب:** {reason}", ORANGE)
    await send_log(guild, embed)
    return True


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    perms = message.author.guild_permissions
    exempt = perms.administrator or perms.manage_messages
    if not exempt and cfg(message.guild, "automod") == "on":
        if await run_automod(message):
            return

    if C_RE.match(message.content.strip()):
        cmd_channel = find_text(message.guild, cfg(message.guild, "commands_channel"))
        if cmd_channel and message.channel.id == cmd_channel.id:
            who = message.mentions[0] if message.mentions else message.author
            await message.reply(embed=credit_embed(message.guild, who), mention_author=False)
            return

    key = (message.guild.id, message.author.id)
    now = time.time()
    if now - last_xp.get(key, 0) < XP_COOLDOWN:
        return
    last_xp[key] = now
    old, new, _ = add_xp(message.guild.id, message.author.id, random.randint(15, 25))
    if new > old:
        add_coins(message.guild.id, message.author.id, 50)
        await announce_level(message.guild, message.author, new, message.channel)
        await check_level_roles(message.author, new)


# ============================================================
#        حلقة الخلفية: الرسائل التلقائية والهدايا
# ============================================================
@tasks.loop(minutes=1)
async def background_loop():
    now = time.time()
    changed = False
    for post in list(DATA["autoposts"]):
        if now >= post["next"]:
            channel = bot.get_channel(post["channel_id"])
            if channel:
                try:
                    await channel.send(post["text"])
                except discord.HTTPException:
                    pass
            if post.get("once"):
                DATA["autoposts"].remove(post)
            else:
                post["next"] = now + post["hours"] * 3600
            changed = True
    if changed:
        save_data()

    for message_id, g in list(DATA["giveaways"].items()):
        if not g["ended"] and now >= g["end"]:
            await end_giveaway(message_id, g)


@background_loop.before_loop
async def before_background():
    await bot.wait_until_ready()


# ============================================================
#                      أوامر الإعداد
# ============================================================
class ResetConfirmView(discord.ui.View):
    def __init__(self, user_id: int, keep_channel_id: int):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.keep_channel_id = keep_channel_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("هذا الزر لصاحب الأمر فقط.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="نعم، احذف كل شيء", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="⏳ جاري الحذف، لا تغلق البوت...", view=self)
        guild = interaction.guild
        protected = {self.keep_channel_id}
        for special in (guild.rules_channel, guild.public_updates_channel):
            if special:
                protected.add(special.id)

        deleted = failed = 0
        for ch in list(guild.channels):
            if isinstance(ch, discord.CategoryChannel) or ch.id in protected:
                continue
            try:
                await ch.delete(reason="reset_channels")
                deleted += 1
            except discord.HTTPException:
                failed += 1
            await asyncio.sleep(0.4)
        for cat in list(guild.categories):
            try:
                await cat.delete(reason="reset_channels")
                deleted += 1
            except discord.HTTPException:
                failed += 1
            await asyncio.sleep(0.4)

        msg = f"✅ تم حذف {deleted} روم/قسم."
        if failed:
            msg += f"\n⚠️ تعذّر حذف {failed} (غالباً رومات المجتمع أو صلاحيات ناقصة)."
        msg += "\nالروم الحالي بقي، احذفه يدوياً. ثم شغّل /setup_server لبناء السيرفر من جديد."
        await interaction.edit_original_response(content=msg, view=None)
        self.stop()

    @discord.ui.button(label="إلغاء", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="تم الإلغاء.", view=None)
        self.stop()


@bot.tree.command(name="reset_channels", description="⚠️ حذف كل الرومات والأقسام")
@app_commands.default_permissions(administrator=True)
async def reset_channels(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("للأدمن فقط.", ephemeral=True)
        return
    view = ResetConfirmView(interaction.user.id, interaction.channel_id)
    await interaction.response.send_message(
        "⚠️ **تحذير:** سيتم حذف **كل** الرومات والأقسام ولا يمكن التراجع.\n"
        "الرتب والأعضاء لن يُحذفوا. هل أنت متأكد؟",
        view=view, ephemeral=True)


@bot.tree.command(name="setup_server", description="تجهيز السيرفر: الرتب والرومات بالزخرفة (يعيد تسمية الموجود ويضيف الناقص)")
@app_commands.default_permissions(administrator=True)
async def setup_server(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    renamed = created = 0

    for name, colour, perms, hoist in ROLES_TO_CREATE:
        if not discord.utils.get(guild.roles, name=name):
            await guild.create_role(name=name, colour=colour, permissions=perms, hoist=hoist)
    mod = discord.utils.get(guild.roles, name=MOD_ROLE)

    for cat_name, data in LAYOUT.items():
        target = styled_category(cat_name)
        category = find_category(guild, cat_name)
        if category is None:
            cat_overwrites = {}
            if cat_name in PRIVATE_CATEGORIES:
                cat_overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
                if mod:
                    cat_overwrites[mod] = discord.PermissionOverwrite(view_channel=True)
            category = await guild.create_category(target, overwrites=cat_overwrites)
            created += 1
            await asyncio.sleep(0.7)
        elif category.name != target:
            await category.edit(name=target)
            renamed += 1
            await asyncio.sleep(0.7)

        for kind in ("text", "voice"):
            finder = find_text if kind == "text" else find_voice
            for ch in data.get(kind, []):
                target_ch = styled_channel(cat_name, ch)
                existing = finder(guild, ch)
                if existing:
                    if existing.name != target_ch:
                        await existing.edit(name=target_ch)
                        renamed += 1
                        await asyncio.sleep(0.7)
                    continue
                if kind == "text":
                    overwrites = {}
                    if ch in READ_ONLY:
                        overwrites[guild.default_role] = discord.PermissionOverwrite(send_messages=False)
                        overwrites[guild.me] = discord.PermissionOverwrite(
                            send_messages=True, embed_links=True, attach_files=True)
                    await category.create_text_channel(target_ch, overwrites=overwrites)
                else:
                    await category.create_voice_channel(target_ch)
                created += 1
                await asyncio.sleep(0.7)

    await interaction.followup.send(
        f"✅ تم! أعدت تسمية {renamed} وأنشأت {created}", ephemeral=True)


@bot.tree.command(name="setup_roles", description="نشر أزرار اختيار الألعاب في هذا الروم")
@app_commands.default_permissions(administrator=True)
async def setup_roles(interaction: discord.Interaction):
    embed = make_embed("🎮 اختر ألعابك",
                       f"اضغط على الزر لتحصل على رتبة اللعبة.\nاضغط مرة ثانية لإزالتها.\n{LINE}", PRIMARY)
    await interaction.channel.send(embed=embed, view=RolesView())
    await interaction.response.send_message("✅ تم", ephemeral=True)


@bot.tree.command(name="setup_tickets", description="نشر قائمة فتح التذاكر في هذا الروم")
@app_commands.default_permissions(administrator=True)
async def setup_tickets(interaction: discord.Interaction):
    embed = make_embed("🎫 مركز المساعدة",
                       f"## تحتاج مساعدة؟\nاختر نوع التذكرة من القائمة وبيفتح لك روم خاص مع الإدارة.\n{LINE}",
                       GREEN)
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("✅ تم", ephemeral=True)


@bot.tree.command(name="welcome_test", description="معاينة رسالة الترحيب بنفسك")
@app_commands.default_permissions(administrator=True)
async def welcome_test(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    embed, file = await build_welcome(interaction.user)
    kwargs = {"file": file} if file else {}
    await interaction.followup.send(embed=embed, ephemeral=True, **kwargs)


@bot.tree.command(name="config_set", description="تغيير إعداد من إعدادات البوت")
@app_commands.describe(key="الإعداد", value="القيمة الجديدة")
@app_commands.choices(key=[app_commands.Choice(name=k, value=k) for k in DEFAULT_CONFIG])
@app_commands.default_permissions(administrator=True)
async def config_set(interaction: discord.Interaction, key: app_commands.Choice[str], value: str):
    DATA["config"].setdefault(str(interaction.guild.id), {})[key.value] = value
    save_data()
    await interaction.response.send_message(f"✅ {key.value} = `{value}`", ephemeral=True)


@bot.tree.command(name="config_show", description="عرض إعدادات البوت")
@app_commands.default_permissions(administrator=True)
async def config_show(interaction: discord.Interaction):
    lines = [f"**{k}:** `{cfg(interaction.guild, k) or '—'}`" for k in DEFAULT_CONFIG]
    await interaction.response.send_message(
        embed=make_embed("⚙️ الإعدادات", "\n".join(lines), PRIMARY), ephemeral=True)


# ============================================================
#                   الإعلانات والفعاليات
# ============================================================
@bot.tree.command(name="announce", description="إرسال إعلان منسق في روم")
@app_commands.describe(title="العنوان", text="نص الإعلان", channel="الروم (الأخبار إذا تركته فاضي)",
                       ping_everyone="منشن للجميع؟")
@app_commands.default_permissions(administrator=True)
async def announce(interaction: discord.Interaction, title: str, text: str,
                   channel: Optional[discord.TextChannel] = None, ping_everyone: bool = False):
    channel = (channel or find_text(interaction.guild, cfg(interaction.guild, "news_channel"))
               or interaction.channel)
    embed = make_embed(f"📢 {title}", f"{text}\n{LINE}", GOLD)
    await channel.send(content="@everyone" if ping_everyone else None, embed=embed,
                       allowed_mentions=discord.AllowedMentions(everyone=ping_everyone))
    await interaction.response.send_message("✅ تم إرسال الإعلان", ephemeral=True)


@bot.tree.command(name="autopost_add", description="رسالة تلقائية تتكرر كل عدد ساعات")
@app_commands.describe(channel="الروم", hours="كل كم ساعة", text="نص الرسالة")
@app_commands.default_permissions(administrator=True)
async def autopost_add(interaction: discord.Interaction, channel: discord.TextChannel,
                       hours: app_commands.Range[int, 1, 168], text: str):
    DATA["autoposts"].append({"guild_id": interaction.guild.id, "channel_id": channel.id,
                              "text": text, "hours": hours, "next": time.time() + hours * 3600})
    save_data()
    await interaction.response.send_message(
        f"✅ بترسل الرسالة في {channel.mention} كل {hours} ساعة", ephemeral=True)


@bot.tree.command(name="autopost_list", description="عرض الرسائل التلقائية")
@app_commands.default_permissions(administrator=True)
async def autopost_list(interaction: discord.Interaction):
    posts = guild_posts(interaction.guild.id)
    if not posts:
        return await interaction.response.send_message("ما في رسائل تلقائية.", ephemeral=True)
    lines = []
    for i, p in enumerate(posts, 1):
        kind = "مرة وحدة" if p.get("once") else f"كل {p['hours']} ساعة"
        lines.append(f"**{i}.** <#{p['channel_id']}> {kind}: {p['text'][:50]}")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="autopost_remove", description="حذف رسالة تلقائية بالرقم")
@app_commands.describe(number="الرقم من /autopost_list")
@app_commands.default_permissions(administrator=True)
async def autopost_remove(interaction: discord.Interaction, number: int):
    posts = guild_posts(interaction.guild.id)
    if number < 1 or number > len(posts):
        return await interaction.response.send_message("❌ رقم غير صحيح.", ephemeral=True)
    DATA["autoposts"].remove(posts[number - 1])
    save_data()
    await interaction.response.send_message("🗑 تم الحذف", ephemeral=True)


@bot.tree.command(name="remind", description="تذكير بفعالية: رسالة مرة وحدة بعد عدد دقائق")
@app_commands.describe(channel="الروم", minutes="بعد كم دقيقة", text="نص التذكير")
@app_commands.default_permissions(administrator=True)
async def remind(interaction: discord.Interaction, channel: discord.TextChannel,
                 minutes: app_commands.Range[int, 1, 10080], text: str):
    DATA["autoposts"].append({"guild_id": interaction.guild.id, "channel_id": channel.id,
                              "text": text, "hours": 0, "once": True,
                              "next": time.time() + minutes * 60})
    save_data()
    await interaction.response.send_message(
        f"⏰ بنذكّر في {channel.mention} بعد {minutes} دقيقة", ephemeral=True)


@bot.tree.command(name="giveaway", description="إطلاق فعالية هدايا")
@app_commands.describe(prize="الجائزة", minutes="المدة بالدقائق", winners="عدد الفائزين",
                       channel="الروم (الحالي إذا تركته فاضي)")
@app_commands.default_permissions(administrator=True)
async def giveaway(interaction: discord.Interaction, prize: str,
                   minutes: app_commands.Range[int, 1, 10080],
                   winners: app_commands.Range[int, 1, 10] = 1,
                   channel: Optional[discord.TextChannel] = None):
    channel = (channel or find_text(interaction.guild, cfg(interaction.guild, "events_channel"))
               or interaction.channel)
    end = time.time() + minutes * 60
    embed = make_embed("🎁 فعالية هدايا",
                       f"## {prize}\n{LINE}\n**الفائزون:** {winners}\n"
                       f"**تنتهي:** <t:{int(end)}:R>\nاضغط الزر للمشاركة 👇", GOLD)
    msg = await channel.send(embed=embed, view=GiveawayView())
    DATA["giveaways"][str(msg.id)] = {"channel_id": channel.id, "prize": prize, "end": end,
                                      "winners": winners, "entries": [], "ended": False}
    save_data()
    await interaction.response.send_message("✅ انطلقت الفعالية", ephemeral=True)


@bot.tree.command(name="poll", description="استطلاع رأي (خيارات مفصولة بفاصلة، حتى 5)")
@app_commands.describe(question="السؤال", options="مثال: نعم, لا, ربما")
async def poll(interaction: discord.Interaction, question: str, options: str):
    if not await in_home(interaction, "poll_channel"):
        return
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    opts = [o.strip() for o in options.replace("،", ",").split(",") if o.strip()][:5]
    if len(opts) < 2:
        return await interaction.response.send_message("❌ لازم خيارين على الأقل.", ephemeral=True)
    desc = "\n".join(f"{nums[i]}  {o}" for i, o in enumerate(opts))
    embed = make_embed(f"📊 {question}", f"{desc}\n{LINE}\nصوّت بالضغط على الرقم 👇", PRIMARY)
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    for i in range(len(opts)):
        await msg.add_reaction(nums[i])


# ============================================================
#                       اللاعبون والبطولات
# ============================================================
@bot.tree.command(name="lfg", description="ابحث عن فريق للعب")
@app_commands.describe(game="اللعبة", slots="عدد اللاعبين المطلوب (مع نفسك)", note="ملاحظة (اختياري)")
@app_commands.choices(game=[app_commands.Choice(name=g, value=g) for g in GAME_ROLES])
async def lfg(interaction: discord.Interaction, game: app_commands.Choice[str],
              slots: app_commands.Range[int, 2, 10] = 4, note: str = ""):
    if not await in_home(interaction, "", LFG_CHANNELS.get(game.value)):
        return
    role = discord.utils.get(interaction.guild.roles, name=game.value)
    mention = role.mention if role else ""
    view = SignupView(interaction.user, f"🎮 يبحث عن فريق: {game.value}",
                      note or "من يبي يلعب معي؟", slots)
    await interaction.response.send_message(
        content=mention, embed=view.render(), view=view,
        allowed_mentions=discord.AllowedMentions(roles=True))


@bot.tree.command(name="tournament", description="إنشاء بطولة وتسجيل المشاركين")
@app_commands.describe(name="اسم البطولة", slots="عدد المشاركين", info="التفاصيل (الموعد، الجوائز...)")
@app_commands.default_permissions(administrator=True)
async def tournament(interaction: discord.Interaction, name: str,
                     slots: app_commands.Range[int, 2, 64] = 16, info: str = ""):
    view = SignupView(interaction.user, f"🏆 بطولة: {name}", info or "سجّل مشاركتك بالزر!",
                      slots, owner_joins=False, colour=GOLD)
    target = (find_text(interaction.guild, cfg(interaction.guild, "tournament_channel"))
              or interaction.channel)
    await target.send(embed=view.render(), view=view)
    await interaction.response.send_message(f"✅ انفتح التسجيل في {target.mention}", ephemeral=True)


@bot.tree.command(name="mcserver", description="حالة سيرفر ماينكرافت (Java)")
@app_commands.describe(ip="عنوان السيرفر (أو اتركه فاضي لاستخدام المحفوظ)")
async def mcserver(interaction: discord.Interaction, ip: Optional[str] = None):
    if not await in_home(interaction, "mcserver_channel"):
        return
    ip = ip or cfg(interaction.guild, "mc_ip")
    if not ip:
        return await interaction.response.send_message(
            "❌ اكتب العنوان، أو احفظه بـ /config_set mc_ip", ephemeral=True)
    await interaction.response.defer()
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"https://api.mcsrvstat.us/3/{ip}") as resp:
                data = await resp.json()
    except Exception:
        return await interaction.followup.send("❌ تعذر الاتصال بخدمة الفحص.")
    if not data.get("online"):
        return await interaction.followup.send(
            embed=make_embed("⛏ ماينكرافت", f"**{ip}**\n🔴 السيرفر أوفلاين", RED))
    players = data.get("players", {})
    motd = " ".join(data.get("motd", {}).get("clean", [])) or "—"
    desc = (f"**{ip}**\n🟢 أونلاين\n{LINE}\n"
            f"👥 اللاعبون: **{players.get('online', 0)}/{players.get('max', 0)}**\n"
            f"🧩 النسخة: **{data.get('version', '?')}**\n📝 {motd}")
    await interaction.followup.send(embed=make_embed("⛏ ماينكرافت", desc, GREEN))


# ============================================================
#                    المستويات والاقتصاد
# ============================================================
@bot.tree.command(name="rank", description="شوف مستواك ونقاطك")
@app_commands.describe(member="العضو (اختياري)")
async def rank(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    if not await in_home(interaction, "level_channel"):
        return
    member = member or interaction.user
    user = get_user(interaction.guild.id, member.id)
    xp = user["xp"]
    lvl = level_from_xp(xp)
    need = xp_for_level(lvl + 1)
    base = xp_for_level(lvl)
    filled = int(10 * (xp - base) / max(need - base, 1))
    bar = "🟩" * filled + "⬜" * (10 - filled)
    desc = (f"## المستوى {lvl}\n{bar}\n**النقاط:** {xp} / {need}\n"
            f"**العملات:** {user.get('coins', 0)} 🪙")
    await interaction.response.send_message(
        embed=make_embed(f"📊 {member.display_name}", desc, PRIMARY, thumb=member.display_avatar.url))


@bot.tree.command(name="leaderboard", description="أفضل 10 أعضاء بالنقاط")
async def leaderboard(interaction: discord.Interaction):
    if not await in_home(interaction, "leaderboard_channel"):
        return
    prefix = f"{interaction.guild.id}:"
    items = [(k, v["xp"]) for k, v in DATA["users"].items() if k.startswith(prefix)]
    items.sort(key=lambda x: x[1], reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (key, xp) in enumerate(items[:10]):
        uid = int(key.split(":")[1])
        m = interaction.guild.get_member(uid)
        name = m.display_name if m else f"مستخدم {uid}"
        mark = medals[i] if i < 3 else f"`{i + 1}.`"
        lines.append(f"{mark} **{name}** — مستوى {level_from_xp(xp)} ({xp} نقطة)")
    text = "\n".join(lines) if lines else "ما في أحد بعد، ابدأوا دردشة!"
    await interaction.response.send_message(embed=make_embed("🏆 المتصدرين", text, GOLD))


@bot.tree.command(name="daily", description="مكافأة يومية من العملات")
async def daily(interaction: discord.Interaction):
    if not await in_home(interaction, "daily_channel"):
        return
    await interaction.response.send_message(**daily_response(interaction.guild.id, interaction.user))


@bot.tree.command(name="balance", description="رصيدك (المحفظة + البنك)")
async def balance(interaction: discord.Interaction):
    if not await in_home(interaction, "balance_channel"):
        return
    await interaction.response.send_message(embed=credit_embed(interaction.guild, interaction.user),
                                            ephemeral=True)


@bot.tree.command(name="shop", description="متجر السيرفر")
async def shop(interaction: discord.Interaction):
    if not await in_home(interaction, "shop_channel"):
        return
    await interaction.response.send_message(embed=shop_embed(), view=ShopView(), ephemeral=True)


@bot.tree.command(name="buy", description="شراء عنصر من المتجر")
@app_commands.choices(item=[app_commands.Choice(name=f"{n} - {p} عملة", value=n)
                            for n, p in SHOP.items()])
async def buy(interaction: discord.Interaction, item: app_commands.Choice[str]):
    if not await in_home(interaction, "shop_channel"):
        return
    ok, text = await purchase(interaction.guild, interaction.user, item.value)
    if ok:
        await interaction.response.send_message(embed=make_embed("🛍 تم الشراء", text, GREEN))
    else:
        await interaction.response.send_message(text, ephemeral=True)


# ============================================================
#                         الألعاب
# ============================================================
@bot.tree.command(name="rps", description="حجر ورقة مقص ضد البوت")
async def rps(interaction: discord.Interaction):
    if not await in_home(interaction, "games_channel"):
        return
    await interaction.response.send_message(
        embed=make_embed("✊ حجر ورقة مقص", "اختر حركتك 👇"), view=RPSView(interaction.user))


@bot.tree.command(name="trivia", description="سؤال ألعاب، الصح يعطيك نقاط وعملات")
async def trivia(interaction: discord.Interaction):
    if not await in_home(interaction, "trivia_channel"):
        return
    q = random.choice(QUESTIONS)
    await interaction.response.send_message(
        embed=make_embed("🧠 سؤال", f"**{q['q']}**"), view=TriviaView(interaction.user, q))


@bot.tree.command(name="dice", description="رمي نرد")
@app_commands.describe(sides="عدد الأوجه (الافتراضي 6)")
async def dice(interaction: discord.Interaction, sides: app_commands.Range[int, 2, 1000] = 6):
    if not await in_home(interaction, "games_channel"):
        return
    await interaction.response.send_message(
        embed=make_embed("🎲 النرد", f"## {random.randint(1, sides)}\nمن {sides}", PRIMARY))


@bot.tree.command(name="coin", description="رمي عملة")
async def coin(interaction: discord.Interaction):
    if not await in_home(interaction, "games_channel"):
        return
    await interaction.response.send_message(
        embed=make_embed("🪙 العملة", f"## {random.choice(['صورة', 'كتابة'])}", GOLD))


# ============================================================
#                  الإدارة والتحذيرات
# ============================================================
def mod_embed(title: str, member: discord.abc.User, by: discord.abc.User, reason: str,
              colour: discord.Colour) -> discord.Embed:
    return make_embed(title, f"**العضو:** {member.mention}\n**بواسطة:** {by.mention}\n"
                             f"**السبب:** {reason}", colour)


@bot.tree.command(name="kick", description="طرد عضو")
@app_commands.describe(member="العضو", reason="السبب")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "بدون سبب"):
    try:
        await member.kick(reason=reason)
    except discord.Forbidden:
        return await interaction.response.send_message("❌ ما أقدر أطرده (رتبته أعلى مني).", ephemeral=True)
    embed = mod_embed("👢 تم الطرد", member, interaction.user, reason, ORANGE)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)


@bot.tree.command(name="ban", description="حظر عضو")
@app_commands.describe(member="العضو", reason="السبب")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "بدون سبب"):
    try:
        await member.ban(reason=reason)
    except discord.Forbidden:
        return await interaction.response.send_message("❌ ما أقدر أحظره (رتبته أعلى مني).", ephemeral=True)
    embed = mod_embed("🔨 تم الحظر", member, interaction.user, reason, RED)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)


@bot.tree.command(name="mute", description="كتم عضو بمدة بالدقائق")
@app_commands.describe(member="العضو", minutes="المدة بالدقائق", reason="السبب")
@app_commands.default_permissions(moderate_members=True)
async def mute(interaction: discord.Interaction, member: discord.Member,
               minutes: app_commands.Range[int, 1, 40320], reason: str = "بدون سبب"):
    try:
        await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
    except discord.Forbidden:
        return await interaction.response.send_message("❌ ما أقدر أكتمه (رتبته أعلى مني).", ephemeral=True)
    embed = mod_embed(f"🔇 تم الكتم ({minutes} دقيقة)", member, interaction.user, reason, ORANGE)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)


@bot.tree.command(name="unmute", description="فك الكتم عن عضو")
@app_commands.default_permissions(moderate_members=True)
async def unmute(interaction: discord.Interaction, member: discord.Member):
    await member.timeout(None)
    await interaction.response.send_message(
        embed=make_embed("🔊 فك الكتم", f"تم فك الكتم عن {member.mention}", GREEN))


@bot.tree.command(name="clear", description="مسح رسائل من الروم")
@app_commands.describe(amount="عدد الرسائل (1-100)")
@app_commands.default_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🧹 تم مسح {len(deleted)} رسالة", ephemeral=True)
    embed = make_embed("🧹 مسح رسائل",
                       f"**بواسطة:** {interaction.user.mention}\n**الروم:** {interaction.channel.mention}\n"
                       f"**العدد:** {len(deleted)}", ORANGE)
    await send_log(interaction.guild, embed)


@bot.tree.command(name="warn", description="تحذير عضو (بعد عدد معين يُكتم تلقائياً)")
@app_commands.describe(member="العضو", reason="السبب")
@app_commands.default_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "بدون سبب"):
    user = get_user(interaction.guild.id, member.id)
    warns = user.setdefault("warns", [])
    warns.append({"reason": reason, "by": interaction.user.id, "time": int(time.time())})
    try:
        limit = int(cfg(interaction.guild, "max_warns"))
    except ValueError:
        limit = 3
    extra = ""
    if len(warns) >= limit:
        user["warns"] = []
        try:
            await member.timeout(datetime.timedelta(hours=1), reason="وصل الحد الأقصى للتحذيرات")
            extra = f"\n🔇 وصل {limit} تحذيرات وتم كتمه ساعة."
        except discord.HTTPException:
            extra = "\n⚠️ وصل الحد الأقصى، بس ما قدرت أكتمه."
    save_data()
    embed = mod_embed(f"⚠️ تحذير ({len(warns) if user['warns'] else limit}/{limit})",
                      member, interaction.user, reason + extra, ORANGE)
    await interaction.response.send_message(embed=embed)
    await send_log(interaction.guild, embed)


@bot.tree.command(name="warnings", description="عرض تحذيرات عضو")
@app_commands.default_permissions(moderate_members=True)
async def warnings(interaction: discord.Interaction, member: discord.Member):
    warns = get_user(interaction.guild.id, member.id).get("warns", [])
    if not warns:
        return await interaction.response.send_message("✅ ما عنده تحذيرات.", ephemeral=True)
    lines = [f"**{i}.** {w['reason']} — <t:{w['time']}:R>" for i, w in enumerate(warns, 1)]
    await interaction.response.send_message(
        embed=make_embed(f"⚠️ تحذيرات {member.display_name}", "\n".join(lines), ORANGE), ephemeral=True)


@bot.tree.command(name="clearwarns", description="مسح تحذيرات عضو")
@app_commands.default_permissions(moderate_members=True)
async def clearwarns(interaction: discord.Interaction, member: discord.Member):
    get_user(interaction.guild.id, member.id)["warns"] = []
    save_data()
    await interaction.response.send_message("🧽 تم مسح التحذيرات", ephemeral=True)


@bot.tree.command(name="badword_add", description="إضافة كلمة ممنوعة")
@app_commands.default_permissions(administrator=True)
async def badword_add(interaction: discord.Interaction, word: str):
    words = DATA["badwords"].setdefault(str(interaction.guild.id), [])
    if word.lower() not in words:
        words.append(word.lower())
        save_data()
    await interaction.response.send_message("✅ تمت الإضافة", ephemeral=True)


@bot.tree.command(name="badword_remove", description="حذف كلمة ممنوعة")
@app_commands.default_permissions(administrator=True)
async def badword_remove(interaction: discord.Interaction, word: str):
    words = DATA["badwords"].setdefault(str(interaction.guild.id), [])
    if word.lower() in words:
        words.remove(word.lower())
        save_data()
    await interaction.response.send_message("🗑 تم الحذف", ephemeral=True)


@bot.tree.command(name="badword_list", description="عرض الكلمات الممنوعة")
@app_commands.default_permissions(administrator=True)
async def badword_list(interaction: discord.Interaction):
    words = DATA["badwords"].get(str(interaction.guild.id), [])
    text = "، ".join(words) if words else "ما في كلمات ممنوعة."
    await interaction.response.send_message(text, ephemeral=True)


@bot.tree.command(name="help", description="قائمة أوامر البوت")
async def help_command(interaction: discord.Interaction):
    desc = (
        f"**🎮 ألعاب**\n/rps  /trivia  /dice  /coin\n{LINE}\n"
        "**👥 لاعبون**\n/lfg  /tournament  /mcserver\n"
        f"{LINE}\n**📊 مستويات واقتصاد**\n/rank  /leaderboard  /daily  /balance  /shop  /buy\n/bank  /deposit  /withdraw  /transfer\n💳 اكتب c بروم الأوامر لرصيدك\n"
        f"{LINE}\n**🎉 تفاعل**\n/poll  /giveaway\n"
        f"{LINE}\n**🛡 إدارة**\n/kick  /ban  /mute  /unmute  /clear  /warn  /warnings  /clearwarns\n"
        f"{LINE}\n**⚙️ للأدمن**\n/setup_server  /reset_channels  /setup_roles  /setup_tickets  /announce  /remind\n"
        "/autopost_add  /autopost_list  /autopost_remove  /badword_add  /badword_remove  "
        "/badword_list  /config_set  /config_show  /welcome_test  /setup_economy  /meme_add  "
        "/meme_list  /meme_remove  /meme_now  /dhikr_now"
    )
    await interaction.response.send_message(embed=make_embed("📖 قائمة الأوامر", desc, PRIMARY), ephemeral=True)


# ============================================================
#   المستوى والرصيد والمتجر والمكافأة اليومية والبنك والميمز والأذكار
# ============================================================
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
C_RE = re.compile(r"^c(?:\s+<@!?(\d+)>)?$", re.I)
BANK_RATE = 0.001          # ربح كل ساعة (حوالي 2.4% باليوم)
BANK_BASE_CAP = 50000      # الربح يُحسب على أول 50 ألف فقط
WARN_ITEM = "🧹 مسح تحذير"
MEME_SUBS = ["ArabFunny", "memes", "dankmemes"]


# ---------- رسالة الترقية: دائماً بروم المستوى ----------
async def announce_level(guild: discord.Guild, member: discord.Member, level: int,
                         origin: Optional[discord.abc.GuildChannel] = None):
    target = find_text(guild, cfg(guild, "level_channel")) or origin
    if target is None:
        return
    note = f"\n📍 من {origin.mention}" if origin and target.id != origin.id else ""
    embed = make_embed("🎉 ترقية مستوى",
                       f"## {member.mention}\nوصلت للمستوى **{level}**\n+50 عملة 🪙{note}", GOLD,
                       thumb=member.display_avatar.url)
    try:
        await target.send(embed=embed)
    except discord.HTTPException as error:
        print(f"[WARN] level-up message failed in #{target.name}: {error}")


# ---------- الرصيد (c) ----------
def credit_embed(guild: discord.Guild, member: discord.abc.User) -> discord.Embed:
    user = get_user(guild.id, member.id)
    wallet, bank = user.get("coins", 0), user.get("bank", 0)
    desc = (f"**المحفظة:** {wallet} 🪙\n**البنك:** {bank} 🪙\n{LINE}\n## المجموع: {wallet + bank} 🪙")
    return make_embed(f"💳 رصيد {member.display_name}", desc, GOLD, thumb=member.display_avatar.url)


# ---------- نشر اللوحات الثابتة (ما بتنحذف) ----------
async def post_panel(guild: discord.Guild, cfg_key: str, panel_key: str,
                     embed: discord.Embed, view: discord.ui.View) -> Optional[discord.Message]:
    channel = find_text(guild, cfg(guild, cfg_key))
    if channel is None:
        return None
    panels = DATA.setdefault("panels", {})
    slot = f"{guild.id}:{panel_key}"
    if slot in panels:
        try:
            msg = await channel.fetch_message(panels[slot])
            await msg.edit(embed=embed, view=view)
            return msg
        except discord.HTTPException:
            pass
    msg = await channel.send(embed=embed, view=view)
    panels[slot] = msg.id
    save_data()
    try:
        await msg.pin()
    except discord.HTTPException:
        pass
    return msg


# ---------- المتجر ----------
async def purchase(guild: discord.Guild, member: discord.Member, item: str):
    price = SHOP.get(item)
    if price is None:
        return False, "❌ هالعنصر مو موجود."
    user = get_user(guild.id, member.id)
    if item == WARN_ITEM:
        warns = user.get("warns", [])
        if not warns:
            return False, "✅ ما عندك تحذيرات أصلاً."
        if user.get("coins", 0) < price:
            return False, f"❌ رصيدك ما يكفي. تحتاج {price} 🪙"
        warns.pop(0)
        user["coins"] -= price
        save_data()
        return True, f"🧹 تم مسح تحذير واحد. تبقى لك **{user['coins']}** 🪙"
    role = discord.utils.get(guild.roles, name=item)
    if role and role in member.roles:
        return False, "عندك هذي الرتبة أصلاً ✅"
    if user.get("coins", 0) < price:
        return False, f"❌ رصيدك ما يكفي. تحتاج {price} 🪙"
    try:
        if role is None:
            role = await guild.create_role(name=item, colour=SHOP_COLOURS.get(item, discord.Colour.default()))
        await member.add_roles(role)
    except discord.Forbidden:
        return False, "❌ ما عندي صلاحية أعطيك الرتبة (ارفع رتبة البوت فوق الرتب)."
    user["coins"] -= price
    save_data()
    return True, f"🛍 مبروك! حصلت على **{item}**. تبقى لك **{user['coins']}** 🪙"


def shop_embed() -> discord.Embed:
    lines = [f"**{name}** — {price} 🪙" for name, price in SHOP.items()]
    desc = ("\n".join(lines) + f"\n{LINE}\nاختر من القائمة تحت عشان تشتري 👇\n"
            "💳 تشوف رصيدك بكتابة `c` بروم الأوامر")
    return make_embed("🛒 متجر السيرفر", desc, GOLD)


class ShopSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=name, description=f"{price} عملة", value=name)
                   for name, price in SHOP.items()]
        super().__init__(placeholder="🛒 اختر اللي بدك تشتريه...", options=options, custom_id="shop:buy")

    async def callback(self, interaction: discord.Interaction):
        ok, text = await purchase(interaction.guild, interaction.user, self.values[0])
        await interaction.response.send_message(text, ephemeral=True)
        try:
            await interaction.message.edit(view=ShopView())  # يرجع القائمة لوضعها الأول
        except discord.HTTPException:
            pass


class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ShopSelect())


# ---------- المكافأة اليومية ----------
def daily_response(guild_id: int, member: discord.abc.User) -> dict:
    user = get_user(guild_id, member.id)
    now = time.time()
    last = user.get("last_daily", 0)
    left = last + 20 * 3600 - now
    if left > 0:
        hours, minutes = int(left // 3600), int((left % 3600) // 60)
        return {"content": f"⏳ ارجع بعد {hours} ساعة و{minutes} دقيقة.", "ephemeral": True}
    streak = user.get("daily_streak", 0) + 1 if last and now - last <= 48 * 3600 else 1
    reward = random.randint(100, 200) + min(streak, 7) * 20
    user["last_daily"] = now
    user["daily_streak"] = streak
    total = add_coins(guild_id, member.id, reward)
    desc = (f"{member.mention}\n## +{reward} 🪙\nرصيدك الآن: **{total}**\n"
            f"🔥 أيام متتالية: **{streak}** (كل يوم متتالي يزيد المكافأة)")
    return {"embed": make_embed("🎁 المكافأة اليومية", desc, GREEN)}


def daily_embed() -> discord.Embed:
    desc = ("اضغط الزر كل يوم وخذ عملاتك 🪙\n"
            f"{LINE}\n🔥 كل يوم متتالي بتزيد المكافأة (حتى 7 أيام)\n"
            "⏳ تقدر تستلم مرة كل 20 ساعة تقريباً")
    return make_embed("🎁 المكافأة اليومية", desc, GREEN)


class DailyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎁 استلم مكافأتك", style=discord.ButtonStyle.success, custom_id="daily:claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(**daily_response(interaction.guild.id, interaction.user))


# ---------- البنك ----------
def parse_amount(text: str, available: int) -> Optional[int]:
    t = text.strip().lower().translate(AR_DIGITS).replace(",", "")
    if t in ("all", "الكل", "كل"):
        return available
    return int(t) if t.isdigit() else None


def bank_open_op(guild_id: int, user_id: int):
    user = get_user(guild_id, user_id)
    if user.get("bank_open"):
        return False, "عندك حساب أصلاً ✅"
    user["bank_open"] = True
    user.setdefault("bank", 0)
    save_data()
    return True, "🏦 تم فتح حسابك! أودع عملاتك وبتبدأ تربح كل ساعة 💹"


def bank_deposit_op(guild_id: int, user_id: int, text: str):
    user = get_user(guild_id, user_id)
    if not user.get("bank_open"):
        return False, "افتح حساب أول بزر **🏦 فتح حساب**."
    amount = parse_amount(text, user.get("coins", 0))
    if not amount or amount <= 0:
        return False, "❌ اكتب رقم صحيح."
    if amount > user.get("coins", 0):
        return False, "❌ رصيدك بالمحفظة ما يكفي."
    user["coins"] -= amount
    user["bank"] = user.get("bank", 0) + amount
    save_data()
    return True, f"💰 تم إيداع **{amount}** 🪙. رصيد البنك: **{user['bank']}**"


def bank_withdraw_op(guild_id: int, user_id: int, text: str):
    user = get_user(guild_id, user_id)
    if not user.get("bank_open"):
        return False, "افتح حساب أول بزر **🏦 فتح حساب**."
    amount = parse_amount(text, user.get("bank", 0))
    if not amount or amount <= 0:
        return False, "❌ اكتب رقم صحيح."
    if amount > user.get("bank", 0):
        return False, "❌ رصيد البنك ما يكفي."
    user["bank"] -= amount
    user["coins"] = user.get("coins", 0) + amount
    save_data()
    return True, f"💸 تم سحب **{amount}** 🪙. رصيد المحفظة: **{user['coins']}**"


def bank_account_embed(guild: discord.Guild, member: discord.abc.User) -> discord.Embed:
    user = get_user(guild.id, member.id)
    if not user.get("bank_open"):
        return make_embed("🏦 حسابك", "ما عندك حساب بعد. اضغط **🏦 فتح حساب** بلوحة البنك.", PRIMARY)
    desc = (f"**المحفظة:** {user.get('coins', 0)} 🪙\n**البنك:** {user.get('bank', 0)} 🪙\n"
            f"**إجمالي الأرباح:** {user.get('bank_profit', 0)} 🪙\n{LINE}\n💹 الربح بينزل على حسابك كل ساعة")
    return make_embed(f"🏦 حساب {member.display_name}", desc, GREEN, thumb=member.display_avatar.url)


def bank_panel_embed() -> discord.Embed:
    desc = ("🏦 افتح حسابك وأودع عملاتك، والبنك بيعطيك ربح كل ساعة تلقائي!\n"
            f"{LINE}\n💹 الربح: حوالي **2.4% باليوم** على أول {BANK_BASE_CAP} 🪙\n"
            "💰 **إيداع** و 💸 **سحب** بالأزرار (اكتب الكل لكل المبلغ)\n"
            "🔁 التحويل لعضو: `/transfer`\n💳 رصيدك الكلي: اكتب `c` بروم الأوامر")
    return make_embed("🏦 بنك NEXUS", desc, GOLD)


class AmountModal(discord.ui.Modal):
    def __init__(self, action: str):
        super().__init__(title="💰 إيداع" if action == "deposit" else "💸 سحب")
        self.action = action
        self.amount = discord.ui.TextInput(label="المبلغ (أو اكتب: الكل)", placeholder="مثال: 500",
                                           max_length=12)
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        op = bank_deposit_op if self.action == "deposit" else bank_withdraw_op
        ok, text = op(interaction.guild.id, interaction.user.id, self.amount.value)
        await interaction.response.send_message(text, ephemeral=True)


class BankView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🏦 فتح حساب", style=discord.ButtonStyle.success, custom_id="bank:open")
    async def b_open(self, interaction: discord.Interaction, button: discord.ui.Button):
        ok, text = bank_open_op(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(text, ephemeral=True)

    @discord.ui.button(label="💰 إيداع", style=discord.ButtonStyle.primary, custom_id="bank:deposit")
    async def b_deposit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AmountModal("deposit"))

    @discord.ui.button(label="💸 سحب", style=discord.ButtonStyle.secondary, custom_id="bank:withdraw")
    async def b_withdraw(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AmountModal("withdraw"))

    @discord.ui.button(label="📊 حسابي", style=discord.ButtonStyle.secondary, custom_id="bank:info")
    async def b_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=bank_account_embed(interaction.guild, interaction.user), ephemeral=True)


@tasks.loop(minutes=10)
async def bank_loop():
    """أرباح البنك: كل ساعة كاملة بتنضاف (حتى لو انطفى البوت، بيعوّض اللي فاته)"""
    now = time.time()
    last = DATA.get("bank_last")
    if last is None:
        DATA["bank_last"] = now
        save_data()
        return
    hours = int((now - last) // 3600)
    if hours < 1:
        return
    DATA["bank_last"] = now - ((now - last) % 3600)
    for user in DATA["users"].values():
        for _ in range(min(hours, 72)):
            bank = user.get("bank", 0)
            if bank <= 0:
                break
            raw = min(bank, BANK_BASE_CAP) * BANK_RATE + user.get("bank_frac", 0.0)
            gain = int(raw)
            user["bank_frac"] = raw - gain
            if gain:
                user["bank"] = bank + gain
                user["bank_profit"] = user.get("bank_profit", 0) + gain
    save_data()


@bot.tree.command(name="bank", description="حسابك بالبنك")
async def bank_cmd(interaction: discord.Interaction):
    if not await in_home(interaction, "balance_channel"):
        return
    await interaction.response.send_message(
        embed=bank_account_embed(interaction.guild, interaction.user), ephemeral=True)


@bot.tree.command(name="deposit", description="إيداع عملات بالبنك")
@app_commands.describe(amount="المبلغ أو اكتب: الكل")
async def deposit_cmd(interaction: discord.Interaction, amount: str):
    if not await in_home(interaction, "balance_channel"):
        return
    ok, text = bank_deposit_op(interaction.guild.id, interaction.user.id, amount)
    await interaction.response.send_message(text, ephemeral=True)


@bot.tree.command(name="withdraw", description="سحب عملات من البنك")
@app_commands.describe(amount="المبلغ أو اكتب: الكل")
async def withdraw_cmd(interaction: discord.Interaction, amount: str):
    if not await in_home(interaction, "balance_channel"):
        return
    ok, text = bank_withdraw_op(interaction.guild.id, interaction.user.id, amount)
    await interaction.response.send_message(text, ephemeral=True)


@bot.tree.command(name="transfer", description="تحويل عملات من محفظتك لعضو")
@app_commands.describe(member="العضو", amount="المبلغ")
async def transfer_cmd(interaction: discord.Interaction, member: discord.Member,
                       amount: app_commands.Range[int, 1, 1000000]):
    if not await in_home(interaction, "balance_channel"):
        return
    if member.bot or member.id == interaction.user.id:
        return await interaction.response.send_message("❌ ما تقدر تحول لنفسك أو لبوت.", ephemeral=True)
    sender = get_user(interaction.guild.id, interaction.user.id)
    if sender.get("coins", 0) < amount:
        return await interaction.response.send_message("❌ رصيد المحفظة ما يكفي.", ephemeral=True)
    sender["coins"] -= amount
    add_coins(interaction.guild.id, member.id, amount)
    await interaction.response.send_message(
        embed=make_embed("🔁 تحويل ناجح", f"{interaction.user.mention} ➜ {member.mention}\n## {amount} 🪙", GREEN))


@bot.tree.command(name="setup_economy", description="نشر لوحات المتجر والمكافأة اليومية والبنك بالرومات المخصصة")
@app_commands.default_permissions(administrator=True)
async def setup_economy(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    for cfg_key in ("shop_channel", "daily_channel", "balance_channel", "level_channel"):
        ch = find_text(guild, cfg(guild, cfg_key))
        if ch:
            try:
                await ch.set_permissions(guild.me, send_messages=True, embed_links=True, attach_files=True)
                await ch.set_permissions(guild.default_role, send_messages=False)
            except discord.HTTPException:
                pass
    lines = []
    for label, cfg_key, panel_key, embed, view in (
            ("المتجر", "shop_channel", "shop", shop_embed(), ShopView()),
            ("المكافأة اليومية", "daily_channel", "daily", daily_embed(), DailyView()),
            ("البنك", "balance_channel", "bank", bank_panel_embed(), BankView())):
        msg = await post_panel(guild, cfg_key, panel_key, embed, view)
        lines.append(f"✅ {label} ➜ {msg.channel.mention}" if msg else f"❌ {label}: الروم مو موجود")
    lines.append("🔒 قفلت الكتابة بهالرومات (الأزرار والأوامر شغّالة)")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


# ---------- الميمز كل 20 دقيقة ----------
async def fetch_meme() -> Optional[dict]:
    subs = MEME_SUBS[:]
    random.shuffle(subs)
    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for sub in subs:
            try:
                async with session.get(f"https://meme-api.com/gimme/{sub}") as resp:
                    data = await resp.json()
            except Exception:
                continue
            url = data.get("url", "")
            if data.get("nsfw") or data.get("spoiler") or not re.search(r"\.(jpe?g|png|gif|webp)(\?|$)", url, re.I):
                continue
            return data
    return None


async def post_meme(guild: discord.Guild) -> bool:
    channel = find_text(guild, cfg(guild, "meme_channel"))
    if channel is None:
        return False
    clips = DATA.setdefault("meme_clips", [])
    turn = DATA.get("meme_turn", 0)
    DATA["meme_turn"] = turn + 1
    try:
        if clips and turn % 2 == 0:
            await channel.send(f"🎬 {clips[(turn // 2) % len(clips)]}")
            save_data()
            return True
        data = await fetch_meme()
        if data is None:
            if clips:
                await channel.send(f"🎬 {random.choice(clips)}")
                save_data()
                return True
            return False
        embed = discord.Embed(title=str(data.get("title", "ميم"))[:250], url=data.get("postLink"),
                              colour=PRIMARY)
        embed.set_image(url=data["url"])
        embed.set_footer(text="🤣 ميم جديد كل 20 دقيقة")
        await channel.send(embed=embed)
        save_data()
        return True
    except discord.HTTPException as error:
        print(f"[WARN] meme post failed: {error}")
        return False


@tasks.loop(minutes=20)
async def meme_loop():
    if meme_loop.current_loop == 0:
        return
    for guild in bot.guilds:
        await post_meme(guild)


@meme_loop.before_loop
async def before_meme():
    await bot.wait_until_ready()


@bot.tree.command(name="meme_add", description="إضافة رابط مقطع للميمز (فيديو أو يوتيوب)")
@app_commands.describe(url="رابط المقطع")
@app_commands.default_permissions(administrator=True)
async def meme_add(interaction: discord.Interaction, url: str):
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return await interaction.response.send_message("❌ لازم رابط يبدأ بـ http", ephemeral=True)
    clips = DATA.setdefault("meme_clips", [])
    clips.append(url)
    save_data()
    await interaction.response.send_message(f"✅ انضاف. عدد المقاطع: {len(clips)}", ephemeral=True)


@bot.tree.command(name="meme_list", description="عرض مقاطع الميمز المحفوظة")
@app_commands.default_permissions(administrator=True)
async def meme_list(interaction: discord.Interaction):
    clips = DATA.setdefault("meme_clips", [])
    if not clips:
        return await interaction.response.send_message(
            "ما في مقاطع محفوظة، البوت بينزل ميمز من الإنترنت. أضف بـ /meme_add", ephemeral=True)
    text = "\n".join(f"**{i}.** {c[:80]}" for i, c in enumerate(clips, 1))
    await interaction.response.send_message(text[:1900], ephemeral=True)


@bot.tree.command(name="meme_remove", description="حذف مقطع من الميمز بالرقم")
@app_commands.describe(number="الرقم من /meme_list")
@app_commands.default_permissions(administrator=True)
async def meme_remove(interaction: discord.Interaction, number: int):
    clips = DATA.setdefault("meme_clips", [])
    if number < 1 or number > len(clips):
        return await interaction.response.send_message("❌ رقم غير صحيح.", ephemeral=True)
    clips.pop(number - 1)
    save_data()
    await interaction.response.send_message("🗑 تم الحذف", ephemeral=True)


@bot.tree.command(name="meme_now", description="نزّل ميم الحين بروم الميمز (للتجربة)")
@app_commands.default_permissions(administrator=True)
async def meme_now(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    ok = await post_meme(interaction.guild)
    await interaction.followup.send("✅ تم" if ok else "❌ ما قدرت (تأكد من روم الميمز والإنترنت)", ephemeral=True)


# ---------- الأذكار والأحاديث كل 30 دقيقة ----------
ADHKAR = [
    ("حديث", "كلمتان خفيفتان على اللسان، ثقيلتان في الميزان، حبيبتان إلى الرحمن: سبحان الله وبحمده، سبحان الله العظيم", "رواه البخاري ومسلم"),
    ("حديث", "من قال: سبحان الله وبحمده، في يوم مائة مرة، حُطّت خطاياه وإن كانت مثل زبد البحر", "رواه البخاري ومسلم"),
    ("حديث", "لأن أقول: سبحان الله، والحمد لله، ولا إله إلا الله، والله أكبر، أحب إليّ مما طلعت عليه الشمس", "رواه مسلم"),
    ("حديث", "ألا أدلك على كنز من كنوز الجنة؟ لا حول ولا قوة إلا بالله", "رواه البخاري ومسلم"),
    ("حديث", "من صلّى عليّ صلاة صلّى الله عليه بها عشرًا", "رواه مسلم"),
    ("حديث", "والله إني لأستغفر الله وأتوب إليه في اليوم أكثر من سبعين مرة", "رواه البخاري"),
    ("حديث", "أحب الكلام إلى الله أربع: سبحان الله، والحمد لله، ولا إله إلا الله، والله أكبر، لا يضرك بأيهن بدأت", "رواه مسلم"),
    ("حديث", "من رضي بالله ربًّا، وبالإسلام دينًا، وبمحمد رسولًا، وجبت له الجنة", "رواه مسلم"),
    ("حديث", "مثل الذي يذكر ربه والذي لا يذكر ربه مثل الحي والميت", "رواه البخاري"),
    ("حديث", "أفضل الذكر لا إله إلا الله، وأفضل الدعاء الحمد لله", "رواه الترمذي وحسّنه"),
    ("حديث", "من قال: لا إله إلا الله وحده لا شريك له، له الملك وله الحمد، وهو على كل شيء قدير، في يوم مائة مرة، كانت له عدل عشر رقاب، وكُتبت له مائة حسنة، ومُحيت عنه مائة سيئة", "رواه البخاري ومسلم"),
    ("حديث", "الكلمة الطيبة صدقة", "رواه البخاري ومسلم"),
    ("حديث", "خيركم من تعلّم القرآن وعلّمه", "رواه البخاري"),
    ("ذكر", "اللهم أنت ربي لا إله إلا أنت، خلقتني وأنا عبدك، وأنا على عهدك ووعدك ما استطعت، أعوذ بك من شر ما صنعت، أبوء لك بنعمتك علي، وأبوء بذنبي، فاغفر لي فإنه لا يغفر الذنوب إلا أنت", "سيد الاستغفار، رواه البخاري"),
    ("ذكر", "اللهم إنك عفو تحب العفو فاعف عني", "رواه الترمذي"),
    ("ذكر", "اللهم أعنّي على ذكرك وشكرك وحسن عبادتك", "رواه أبو داود والنسائي"),
    ("ذكر", "رب اغفر لي وتب عليّ إنك أنت التواب الرحيم", "رواه أبو داود والترمذي"),
    ("ذكر", "حسبنا الله ونعم الوكيل", "سورة آل عمران: 173"),
    ("ذكر", "لا إله إلا أنت سبحانك إني كنت من الظالمين", "سورة الأنبياء: 87"),
    ("آية", "ألا بذكر الله تطمئن القلوب", "سورة الرعد: 28"),
    ("آية", "فاذكروني أذكركم واشكروا لي ولا تكفرون", "سورة البقرة: 152"),
    ("آية", "والذاكرين الله كثيرًا والذاكرات أعدّ الله لهم مغفرة وأجرًا عظيمًا", "سورة الأحزاب: 35"),
    ("آية", "يا أيها الذين آمنوا اذكروا الله ذكرًا كثيرًا وسبّحوه بكرة وأصيلًا", "سورة الأحزاب: 41-42"),
]
DHIKR_TITLES = {"ذكر": "📿 ذكر", "حديث": "📜 حديث شريف", "آية": "📖 آية"}


async def post_dhikr(guild: discord.Guild) -> bool:
    channel = find_text(guild, cfg(guild, "dhikr_channel"))
    if channel is None:
        return False
    last = DATA.get("last_dhikr", -1)
    idx = random.choice([i for i in range(len(ADHKAR)) if i != last])
    DATA["last_dhikr"] = idx
    kind, text, source = ADHKAR[idx]
    embed = make_embed(DHIKR_TITLES[kind], f"## {text}\n{LINE}\n📚 {source}", GREEN)
    try:
        await channel.send(embed=embed)
        save_data()
        return True
    except discord.HTTPException as error:
        print(f"[WARN] dhikr post failed: {error}")
        return False


@tasks.loop(minutes=30)
async def dhikr_loop():
    if dhikr_loop.current_loop == 0:
        return
    for guild in bot.guilds:
        await post_dhikr(guild)


@dhikr_loop.before_loop
async def before_dhikr():
    await bot.wait_until_ready()


@bot.tree.command(name="dhikr_now", description="نزّل ذكر أو حديث الحين بروم التسبيح (للتجربة)")
@app_commands.default_permissions(administrator=True)
async def dhikr_now(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    ok = await post_dhikr(interaction.guild)
    await interaction.followup.send("✅ تم" if ok else "❌ ما لقيت روم التسبيح", ephemeral=True)



# ============================================================
#              ربط الموقع (Supabase) - البنك والمتجر
# ============================================================
SB_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SB_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")  # مفتاح sb_secret (سر، لا تحطه بالكود)
WEB_GUILD_ID = int(os.environ.get("WEB_GUILD_ID", "0") or 0)
WEB_ENABLED = bool(SB_URL and SB_KEY)


async def sb_req(method: str, path: str, **kw):
    headers = {"apikey": SB_KEY, "Content-Type": "application/json", **kw.pop("headers", {})}
    if SB_KEY.startswith("eyJ"):  # المفاتيح القديمة (JWT) بس بتحتاج Authorization
        headers["Authorization"] = f"Bearer {SB_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.request(method, f"{SB_URL}/rest/v1/{path}", headers=headers, **kw) as resp:
            if resp.status >= 300:
                print("[WEB]", method, path, resp.status, (await resp.text())[:200])
                return None
            if "json" in (resp.content_type or ""):
                return await resp.json()
            return True


def web_guild() -> Optional[discord.Guild]:
    if WEB_GUILD_ID:
        return bot.get_guild(WEB_GUILD_ID)
    return bot.guilds[0] if bot.guilds else None


def balance_row(guild_id: int, user_id: int) -> dict:
    user = get_user(guild_id, user_id)
    return {"discord_id": str(user_id), "coins": user.get("coins", 0), "bank": user.get("bank", 0),
            "bank_open": bool(user.get("bank_open")), "level": level_from_xp(user.get("xp", 0)),
            "updated_at": datetime.datetime.utcnow().isoformat() + "Z"}


async def push_balances(rows: list):
    for i in range(0, len(rows), 400):
        await sb_req("POST", "bot_balances?on_conflict=discord_id", json=rows[i:i + 400],
                     headers={"Prefer": "resolution=merge-duplicates,return=minimal"})


async def sync_balances():
    guild = web_guild()
    if guild is None:
        return
    rows = []
    for key, user in list(DATA["users"].items()):
        gid, uid = key.split(":")
        if gid == str(guild.id) and (user.get("coins") or user.get("bank") or user.get("bank_open")):
            rows.append(balance_row(guild.id, int(uid)))
    if rows:
        await push_balances(rows)
    if web_loop.current_loop == 0:
        print(f"[WEB] الربط شغّال، تمت مزامنة {len(rows)} حساب")


async def sync_shop():
    rows = [{"name": name, "price": price, "active": True,
             "description": "يمسح تحذير واحد من سجلك" if name == WARN_ITEM else "رتبة خاصة بالسيرفر"}
            for name, price in SHOP.items()]
    await sb_req("POST", "store_items?on_conflict=name", json=rows,
                 headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
    names = ",".join('"%s"' % n for n in SHOP)
    await sb_req("PATCH", "store_items", params={"name": f"not.in.({names})"}, json={"active": False})


async def process_orders():
    guild = web_guild()
    if guild is None:
        return
    orders = await sb_req("GET", "web_orders?status=eq.pending&order=created_at&limit=20")
    for order in orders or []:
        ok, msg = False, "نوع الطلب غير معروف."
        uid = int(order["member_id"])
        try:
            member = guild.get_member(uid) or await guild.fetch_member(uid)
        except discord.HTTPException:
            member = None
        if member is None:
            msg = "العضو مو موجود بالسيرفر."
        elif order["kind"] == "open":
            ok, msg = bank_open_op(guild.id, uid)
            ok = True  # لو كان عنده حساب أصلاً، مش مشكلة
        elif order["kind"] == "buy":
            ok, msg = await purchase(guild, member, order["item"])
        elif order["kind"] == "credit":
            user = get_user(guild.id, uid)
            user["coins"] = max(0, user.get("coins", 0) + int(order["amount"] or 0))
            save_data()
            ok, msg = True, f"تم تعديل الرصيد، المحفظة الآن {user['coins']}"
        await sb_req("PATCH", "web_orders", params={"id": f"eq.{order['id']}"},
                     json={"status": "done" if ok else "failed", "result": msg[:300],
                           "done_at": datetime.datetime.utcnow().isoformat() + "Z"})
        await push_balances([balance_row(guild.id, uid)])


@tasks.loop(seconds=15)
async def web_loop():
    if not WEB_ENABLED:
        if web_loop.current_loop == 0:
            print("[WEB] الربط معطّل: ناقص SUPABASE_URL أو SUPABASE_SERVICE_KEY")
        return
    try:
        await process_orders()
        if web_loop.current_loop % 2 == 0:
            await sync_balances()
        if web_loop.current_loop % 20 == 0:
            await sync_shop()
    except Exception as error:
        print("[WEB] error:", error)


@web_loop.before_loop
async def before_web_loop():
    await bot.wait_until_ready()


bot.run(TOKEN)
