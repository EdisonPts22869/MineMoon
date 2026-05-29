import asyncio
import logging
import json
import random
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, BigInteger,
    Float, Text, ForeignKey
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session

# ==================== КОНФИГ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    BOT_TOKEN = "СЮДА_ТОКЕН_ЕСЛИ_НЕТ_ENV"

ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "123456789")
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(",") if id.strip()]

# ==================== БАЗА ДАННЫХ ====================
DB_PATH = "dark_mines.db"
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

# ==================== FSM СОСТОЯНИЯ ====================
class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_ban_reason = State()
    waiting_for_artifact_target = State()
    waiting_for_artifact_type = State()
    waiting_for_artifact_rarity = State()

class FightStates(StatesGroup):
    in_fight = State()

class GameStates(StatesGroup):
    waiting_for_promo_code = State()
    waiting_for_transfer_artifact = State()
    waiting_for_trust_artifact = State()
    waiting_for_artifact_upgrade = State()

# ==================== DP ====================
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
bot = None

# ==================== МОДЕЛИ (сокращённые) ====================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, default="")
    first_name = Column(String, default="")
    title = Column(String, default="Начинающий шахтер")
    last_active = Column(DateTime, default=datetime.now)
    
    arena = Column(Integer, default=1)
    pickaxe_level = Column(Integer, default=1)
    armor_level = Column(Integer, default=1)
    helmet_level = Column(Integer, default=1)
    boots_level = Column(Integer, default=1)
    lantern_level = Column(Integer, default=1)
    coins = Column(Integer, default=5000)
    gems = Column(Integer, default=500)
    exp = Column(Integer, default=0)
    energy = Column(Integer, default=100)
    max_energy = Column(Integer, default=100)
    artifact_slots = Column(Integer, default=3)
    
    health = Column(Integer, default=100)
    max_health = Column(Integer, default=100)
    damage = Column(Integer, default=10)
    defense = Column(Integer, default=0)
    critical_chance = Column(Float, default=0.1)
    critical_damage = Column(Float, default=2.0)
    dodge_chance = Column(Float, default=0.05)
    lifesteal = Column(Float, default=0.0)
    
    vip_level = Column(Integer, default=0)
    vip_purchased_at = Column(DateTime, nullable=True)
    
    last_daily = Column(DateTime, nullable=True)
    daily_streak = Column(Integer, default=0)
    rebirth_count = Column(Integer, default=0)
    rebirth_multiplier = Column(Float, default=1.0)
    
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(String, default="")
    is_admin = Column(Boolean, default=False)
    
    inventory = relationship("Inventory", back_populates="user", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="owner", foreign_keys="Artifact.owner_id")
    
    @property
    def is_vip(self):
        return self.vip_level > 0
    
    @property
    def vip_title(self):
        titles = {0: "Новичок", 1: "Бывалый шахтер", 2: "Старатель", 3: "Золотоискатель", 4: "Хранитель недр", 5: "Властелин шахт"}
        return titles.get(self.vip_level, "Легенда")


class Artifact(Base):
    __tablename__ = "artifacts"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    artifact_type = Column(String, nullable=False)
    rarity = Column(String, default="common")
    level = Column(Integer, default=1)
    max_level = Column(Integer, default=10)
    exp = Column(Integer, default=0)
    
    damage_bonus = Column(Integer, default=0)
    defense_bonus = Column(Integer, default=0)
    health_bonus = Column(Integer, default=0)
    crit_chance_bonus = Column(Float, default=0.0)
    crit_damage_bonus = Column(Float, default=0.0)
    dodge_bonus = Column(Float, default=0.0)
    lifesteal_bonus = Column(Float, default=0.0)
    exp_bonus = Column(Float, default=0.0)
    coin_bonus = Column(Float, default=0.0)
    damage_reduction = Column(Float, default=0.0)
    
    equipped_slot = Column(Integer, default=0)
    trusted_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    trusted_until = Column(DateTime, nullable=True)
    
    owner = relationship("User", back_populates="artifacts", foreign_keys=[owner_id])
    
    @property
    def rarity_color(self):
        colors = {"common": "⬜", "rare": "🟦", "epic": "🟪", "legendary": "🟨", "mythical": "🟥"}
        return colors.get(self.rarity, "⬜")
    
    @property
    def rarity_name(self):
        names = {"common": "Обычный", "rare": "Редкий", "epic": "Эпический", "legendary": "Легендарный", "mythical": "Мифический"}
        return names.get(self.rarity, "Обычный")


class Inventory(Base):
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    item_type = Column(String)
    item_name = Column(String)
    item_level = Column(Integer, default=1)
    quantity = Column(Integer, default=1)
    equipped = Column(Boolean, default=False)
    
    user = relationship("User", back_populates="inventory")


class Arena(Base):
    __tablename__ = "arenas"
    id = Column(Integer, primary_key=True)
    arena_number = Column(Integer, unique=True, nullable=False)
    name = Column(String)
    description = Column(String)
    reward_coins = Column(Integer, default=100)
    reward_exp = Column(Integer, default=50)


class Boss(Base):
    __tablename__ = "bosses"
    id = Column(Integer, primary_key=True)
    arena_id = Column(Integer, ForeignKey("arenas.id"))
    boss_number = Column(Integer)
    name = Column(String)
    title = Column(String)
    health = Column(Integer)
    damage = Column(Integer)
    defense = Column(Integer)
    reward_coins = Column(Integer)
    reward_exp = Column(Integer)
    reward_gems = Column(Integer, default=0)
    drop_material = Column(String)
    drop_chance = Column(Float, default=0.5)
    artifact_drop_chance = Column(Float, default=0.1)


class PromoCode(Base):
    __tablename__ = "promo_codes"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    reward_coins = Column(Integer, default=0)
    reward_gems = Column(Integer, default=0)
    reward_item = Column(String, nullable=True)
    uses_limit = Column(Integer, default=1)
    uses_count = Column(Integer, default=0)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    is_permanent = Column(Boolean, default=False)


class PromoUsed(Base):
    __tablename__ = "promo_used"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    promo_id = Column(Integer, ForeignKey("promo_codes.id"))
    used_at = Column(DateTime, default=datetime.now)


# ==================== 60 АРТЕФАКТОВ (сокращённый список) ====================

ARTIFACTS = {
    "ring": [
        {"name": "Кольцо шахтера", "rarity": "common", "damage_bonus": 5, "defense_bonus": 3},
        {"name": "Кольцо удачи", "rarity": "rare", "crit_chance_bonus": 0.05, "coin_bonus": 0.1},
        {"name": "Кольцо вампира", "rarity": "epic", "lifesteal_bonus": 0.1, "damage_bonus": 15},
        {"name": "Кольцо невидимости", "rarity": "legendary", "dodge_bonus": 0.15, "defense_bonus": 20},
        {"name": "Кольцо всевластия", "rarity": "mythical", "damage_bonus": 50, "defense_bonus": 50, "health_bonus": 500},
    ],
    "amulet": [
        {"name": "Амулет здоровья", "rarity": "common", "health_bonus": 100},
        {"name": "Амулет силы", "rarity": "rare", "damage_bonus": 20, "health_bonus": 50},
        {"name": "Амулет защиты", "rarity": "rare", "defense_bonus": 25, "damage_reduction": 0.08},
        {"name": "Амулет критов", "rarity": "epic", "crit_chance_bonus": 0.12, "crit_damage_bonus": 0.5},
        {"name": "Амулет дракона", "rarity": "legendary", "damage_bonus": 35, "defense_bonus": 35, "health_bonus": 350},
    ],
    "stone": [
        {"name": "Камень удачи", "rarity": "common", "coin_bonus": 0.15},
        {"name": "Камень опыта", "rarity": "rare", "exp_bonus": 0.25},
        {"name": "Рубин крови", "rarity": "epic", "lifesteal_bonus": 0.12, "damage_bonus": 18},
        {"name": "Сапфир магии", "rarity": "epic", "defense_bonus": 30, "damage_reduction": 0.1},
        {"name": "Алмаз чистоты", "rarity": "legendary", "damage_bonus": 40, "defense_bonus": 30, "health_bonus": 200},
    ],
    "scroll": [
        {"name": "Свиток мудрости", "rarity": "common", "exp_bonus": 0.2},
        {"name": "Свиток богатства", "rarity": "rare", "coin_bonus": 0.25, "exp_bonus": 0.1},
        {"name": "Свиток войны", "rarity": "epic", "damage_bonus": 25, "crit_damage_bonus": 0.4},
        {"name": "Свиток защиты", "rarity": "rare", "defense_bonus": 20, "damage_reduction": 0.05},
        {"name": "Свиток вампира", "rarity": "epic", "lifesteal_bonus": 0.15, "health_bonus": 150},
    ],
    "crystal": [
        {"name": "Кристалл маны", "rarity": "common", "health_bonus": 80},
        {"name": "Кристалл силы", "rarity": "rare", "damage_bonus": 15, "crit_damage_bonus": 0.2},
        {"name": "Кристалл защиты", "rarity": "rare", "defense_bonus": 18, "damage_reduction": 0.05},
        {"name": "Кристалл жизни", "rarity": "epic", "health_bonus": 250, "lifesteal_bonus": 0.08},
        {"name": "Кристалл удачи", "rarity": "epic", "crit_chance_bonus": 0.1, "coin_bonus": 0.2},
    ],
    "rune": [
        {"name": "Руна огня", "rarity": "common", "damage_bonus": 8},
        {"name": "Руна льда", "rarity": "common", "defense_bonus": 8},
        {"name": "Руна жизни", "rarity": "rare", "health_bonus": 150, "lifesteal_bonus": 0.05},
        {"name": "Руна смерти", "rarity": "epic", "damage_bonus": 20, "crit_damage_bonus": 0.3, "lifesteal_bonus": 0.1},
        {"name": "Руна скорости", "rarity": "rare", "dodge_bonus": 0.1, "exp_bonus": 0.1},
    ],
}

# ==================== VIP НАБОРЫ ====================

VIP_SETS = {
    1: {"name": "Набор Бывалого шахтера", "items": [("weapon", "Стальная кирка", 1), ("armor", "Кожаная броня", 1), ("material", "Шахтерское зелье", 5)], "coins": 1000, "gems": 100, "artifact_type": "ring", "artifact_rarity": "common"},
    2: {"name": "Набор Старателя", "items": [("weapon", "Мифриловая кирка", 1), ("armor", "Кольчужная броня", 1), ("helmet", "Каска старателя", 1), ("material", "Эликсир бодрости", 10)], "coins": 3000, "gems": 300, "artifact_type": "amulet", "artifact_rarity": "rare"},
    3: {"name": "Набор Золотоискателя", "items": [("weapon", "Золотая кирка", 1), ("armor", "Латная броня", 1), ("helmet", "Золотая каска", 1), ("boots", "Сапоги рудокопа", 1), ("material", "Зелье удачи", 15)], "coins": 5000, "gems": 500, "artifact_type": "stone", "artifact_rarity": "epic"},
    4: {"name": "Набор Хранителя недр", "items": [("weapon", "Алмазная кирка", 1), ("armor", "Драконья броня", 1), ("helmet", "Шлем титана", 1), ("boots", "Ботинки скорости", 1), ("lantern", "Фонарь хранителя", 1), ("material", "Эликсир мощи", 20)], "coins": 10000, "gems": 1000, "artifact_type": "scroll", "artifact_rarity": "legendary"},
    5: {"name": "Набор Властелина шахт", "items": [("weapon", "Кирка бога", 1), ("armor", "Броня титана", 1), ("helmet", "Корона шахт", 1), ("boots", "Сапоги властелина", 1), ("lantern", "Фонарь бездны", 1), ("material", "Зелье бессмертия", 30), ("special", "Титул Король шахт", 1)], "coins": 50000, "gems": 5000, "artifact_type": "crystal", "artifact_rarity": "mythical"},
}

# ==================== 50 ШАХТ ====================

ARENAS = [
    (1, "🏔 Заброшенная штольня", "Старая выработка", 100, 50),
    (2, "🔥 Огненный карьер", "Лавовые озера", 150, 75),
    (3, "❄ Мерзлая пещера", "Ледяные гроты", 200, 100),
    (4, "🌲 Таежный прииск", "Золотоносные жилы", 250, 125),
    (5, "⚡ Грозовой разлом", "Ущелье молний", 300, 150),
    (10, "🏰 Каменоломня великанов", "Следы цивилизации", 550, 275),
    (15, "👁 Око бездны", "Бездонная шахта", 800, 400),
    (20, "🌟 Астральный разлом", "Редчайшие руды", 1050, 525),
    (25, "🔮 Хрустальный грот", "Магические кристаллы", 1300, 650),
    (30, "⛓ Цепи Тартара", "Врата в преисподнюю", 1550, 775),
    (35, "🦅 Орлиное гнездо", "Заоблачный пик", 1800, 900),
    (40, "🏛 Храм забвения", "Руины богов", 2050, 1025),
    (45, "⚗ Алхимический цех", "Философский камень", 2300, 1150),
    (50, "👑 Тронный зал глубин", "Последняя шахта", 3000, 1500),
]

BOSSES = {}
for arena_num, _, _, _, _ in ARENAS:
    BOSSES[arena_num] = [
        (f"Хранитель {arena_num}", "Страж", 500+arena_num*80, 60+arena_num*5, 15+arena_num//3, 400+arena_num*40, 150+arena_num*20, f"Руда {arena_num}", 0.4, None, 0, 0.05),
        (f"Старатель {arena_num}", "Проклятый", 700+arena_num*100, 80+arena_num*6, 20+arena_num//2, 600+arena_num*50, 200+arena_num*25, "Слиток", 0.35, None, 0, 0.06),
        (f"Владыка {arena_num}", "Повелитель", 1000+arena_num*150, 120+arena_num*8, 30+arena_num*2, 900+arena_num*60, 300+arena_num*35, "Самородок", 0.3, None, 0, 0.1),
    ]

# Особые боссы для первых шахт
BOSSES[1] = [
    ("Крот-мутант", "Вредитель", 150, 25, 5, 200, 80, "Железная руда", 0.5, None, 0, 0.05),
    ("Каменный голем", "Страж", 250, 35, 8, 300, 100, "Медная руда", 0.4, None, 0, 0.07),
    ("Теневой шахтер", "Проклятый", 350, 45, 10, 400, 120, "Серебряная руда", 0.6, "⭐ Кольцо", 0.05, 0.1),
]

# ==================== СУМКИ С АРТЕФАКТАМИ ====================

ARTIFACT_BAG = {"name": "🎒 Сумка", "price_coins": 5000, "price_gems": 100, "required_vip": 0, "count": 1, "weights": {"common": 0.50, "rare": 0.30, "epic": 0.15, "legendary": 0.04, "mythical": 0.01}}
ARTIFACT_SUITCASE = {"name": "🧳 Чемодан", "price_coins": 0, "price_gems": 500, "required_vip": 2, "count": 3, "weights": {"common": 0.20, "rare": 0.35, "epic": 0.25, "legendary": 0.15, "mythical": 0.05}}
ARTIFACT_ELITE = {"name": "👑 Элитный", "price_coins": 0, "price_gems": 2000, "required_vip": 5, "count": 5, "weights": {"common": 0.05, "rare": 0.15, "epic": 0.25, "legendary": 0.35, "mythical": 0.20}}

# ==================== ФУНКЦИИ ====================

def init_db():
    Base.metadata.create_all(engine)
    session = SessionLocal()
    for a in ARENAS:
        if not session.query(Arena).filter(Arena.arena_number == a[0]).first():
            session.add(Arena(arena_number=a[0], name=a[1], description=a[2], reward_coins=a[3], reward_exp=a[4]))
    session.commit()
    for an, bs in BOSSES.items():
        ar = session.query(Arena).filter(Arena.arena_number == an).first()
        if ar:
            for i, bd in enumerate(bs, 1):
                if not session.query(Boss).filter(Boss.arena_id == ar.id, Boss.boss_number == i).first():
                    session.add(Boss(arena_id=ar.id, boss_number=i, name=bd[0], title=bd[1], health=bd[2], damage=bd[3], defense=bd[4], reward_coins=bd[5], reward_exp=bd[6], drop_material=bd[7], drop_chance=bd[8], artifact_drop_chance=bd[11] if len(bd)>11 else 0.1))
    session.commit()
    session.close()

def get_user(session, tg_id, create=True):
    u = session.query(User).filter(User.user_id == tg_id).first()
    if not u and create:
        u = User(user_id=tg_id)
        session.add(u)
        session.commit()
        for it in [("weapon","Кирка новичка",1,True), ("armor","Роба шахтера",1,True), ("material","Пайка шахтера",5,False)]:
            session.add(Inventory(user_id=u.id, item_type=it[0], item_name=it[1], quantity=it[2], equipped=it[3]))
        session.commit()
    return u

def update_stats(u):
    bd = 10+(u.pickaxe_level-1)*4+(u.rebirth_count*8)
    bdf = 5+(u.armor_level-1)*3+(u.helmet_level-1)*2+(u.boots_level-1)*1+(u.rebirth_count*4)
    bh = 100+(u.armor_level-1)*15+(u.helmet_level-1)*10+(u.rebirth_count*25)
    cc, cd, dc, ls = 0.1, 2.0, 0.05, 0.0
    s = SessionLocal()
    for a in s.query(Artifact).filter(Artifact.owner_id==u.id, Artifact.equipped_slot>0).all():
        bd+=a.damage_bonus; bdf+=a.defense_bonus; bh+=a.health_bonus
        cc+=a.crit_chance_bonus; cd+=a.crit_damage_bonus; dc+=a.dodge_bonus; ls+=a.lifesteal_bonus
    s.close()
    if u.is_vip:
        m={1:1.1,2:1.2,3:1.35,4:1.5,5:2.0}.get(u.vip_level,1.0)
        bd=int(bd*m); bdf=int(bdf*m); bh=int(bh*m)
        cc+=0.05+u.vip_level*0.03; cd+=0.2+u.vip_level*0.2; dc+=0.05+u.vip_level*0.02; ls+=0.05*u.vip_level
    u.damage=bd; u.defense=bdf; u.max_health=bh
    u.critical_chance=min(cc,0.8); u.critical_damage=min(cd,5.0)
    u.dodge_chance=min(dc,0.5); u.lifesteal=min(ls,0.5)
    u.max_energy=100+(u.lantern_level-1)*20

def create_artifact(oid, weights=None):
    if not weights: weights={"common":0.5,"rare":0.3,"epic":0.13,"legendary":0.05,"mythical":0.02}
    r=random.choices(list(weights.keys()),weights=list(weights.values()))[0]
    t=random.choice(list(ARTIFACTS.keys()))
    av=[a for a in ARTIFACTS[t] if a["rarity"]==r] or ARTIFACTS[t]
    tp=random.choice(av)
    s=SessionLocal()
    art=Artifact(owner_id=oid, name=tp["name"], artifact_type=t, rarity=r, damage_bonus=tp.get("damage_bonus",0), defense_bonus=tp.get("defense_bonus",0), health_bonus=tp.get("health_bonus",0), crit_chance_bonus=tp.get("crit_chance_bonus",0.0), crit_damage_bonus=tp.get("crit_damage_bonus",0.0), dodge_bonus=tp.get("dodge_bonus",0.0), lifesteal_bonus=tp.get("lifesteal_bonus",0.0), exp_bonus=tp.get("exp_bonus",0.0), coin_bonus=tp.get("coin_bonus",0.0), damage_reduction=tp.get("damage_reduction",0.0))
    s.add(art); s.commit(); s.refresh(art); s.close()
    return art

def open_pack(u, cfg):
    return [create_artifact(u.id, cfg["weights"]) for _ in range(cfg["count"])]

def is_admin(uid): return uid in ADMIN_IDS

def main_menu():
    b=InlineKeyboardBuilder()
    for t,c in [("🏟 Шахты","menu_arenas"),("👤 Профиль","menu_profile"),("🎒 Сумка","menu_bag"),("🧳 Чемодан","menu_case"),("👑 Элитный","menu_elite"),("🎟 Промокод","menu_promo"),("💎 Магазин","menu_donate"),("❓ Помощь","menu_help")]:
        b.button(text=t, callback_data=c)
    b.adjust(2)
    return b.as_markup()

def fight_kb(boss, an, bn):
    b=InlineKeyboardBuilder()
    b.button(text="⚔️ Атаковать", callback_data=f"atk_{an}_{bn}")
    b.button(text="💊 Зелье", callback_data=f"pot_{an}_{bn}")
    b.button(text="🏃 Сбежать", callback_data="menu_arenas")
    b.adjust(2)
    return b.as_markup()

active_fights = {}

# ==================== MIDDLEWARE ====================

@dp.message.middleware()
async def ban_mw(handler, event: Message, data: dict):
    s=SessionLocal()
    u=s.query(User).filter(User.user_id==event.from_user.id).first()
    s.close()
    if u and u.is_banned:
        await event.answer(f"⛔ Бан: {u.ban_reason}")
        return
    return await handler(event, data)

# ==================== ХЭНДЛЕРЫ ====================

@dp.message(Command("start"))
async def start(msg: Message):
    s=SessionLocal()
    u=get_user(s, msg.from_user.id)
    u.first_name=msg.from_user.first_name or ""
    u.username=msg.from_user.username or ""
    u.last_active=datetime.now()
    s.commit(); s.close()
    await msg.answer("⛏ **ТЕМНЫЕ ШАХТЫ**\nДобро пожаловать!\n/menu - меню", reply_markup=main_menu())

@dp.message(Command("menu"))
async def menu(msg: Message):
    await msg.answer("⛏ Меню", reply_markup=main_menu())

@dp.message(Command("profile"))
async def profile(msg: Message):
    s=SessionLocal()
    u=get_user(s, msg.from_user.id)
    update_stats(u); s.commit()
    await msg.answer(f"⛏ {u.first_name or u.username}\n🏅 {u.vip_title} (ур.{u.vip_level})\n⚔️ Урон: {u.damage} | 🛡 Защита: {u.defense}\n❤️ HP: {u.health}/{u.max_health}\n💰 Золото: {u.coins} | 💎 Самоцветы: {u.gems}\n🏟 Шахта: {u.arena}/50")
    s.close()

@dp.callback_query(F.data=="menu_main")
async def cb_main(cb: CallbackQuery):
    await cb.message.edit_text("⛏ Меню", reply_markup=main_menu())
    await cb.answer()

@dp.callback_query(F.data=="menu_profile")
async def cb_profile(cb: CallbackQuery):
    s=SessionLocal()
    u=get_user(s, cb.from_user.id)
    update_stats(u); s.commit(); s.close()
    await cb.message.edit_text(f"⛏ {u.first_name or u.username}\n🏅 {u.vip_title}\n⚔️ Урон: {u.damage}\n💰 Золото: {u.coins}\n🏟 Шахта: {u.arena}/50", reply_markup=main_menu())
    await cb.answer()

# Сумки с артефактами
@dp.callback_query(F.data=="menu_bag")
async def cb_bag(cb: CallbackQuery):
    s=SessionLocal()
    u=get_user(s, cb.from_user.id)
    if u.coins<ARTIFACT_BAG["price_coins"]:
        await cb.answer("❌ Мало золота!", show_alert=True); s.close(); return
    u.coins-=ARTIFACT_BAG["price_coins"]
    arts=open_pack(u, ARTIFACT_BAG)
    s.commit(); s.close()
    txt="🎒 **Сумка открыта!**\n"+"\n".join(f"{a.rarity_color} {a.name}" for a in arts)
    await cb.message.edit_text(txt, reply_markup=main_menu())
    await cb.answer()

@dp.callback_query(F.data=="menu_case")
async def cb_case(cb: CallbackQuery):
    s=SessionLocal()
    u=get_user(s, cb.from_user.id)
    if u.vip_level<ARTIFACT_SUITCASE["required_vip"]:
        await cb.answer("❌ Нужен VIP!", show_alert=True); s.close(); return
    if u.gems<ARTIFACT_SUITCASE["price_gems"]:
        await cb.answer("❌ Мало самоцветов!", show_alert=True); s.close(); return
    u.gems-=ARTIFACT_SUITCASE["price_gems"]
    arts=open_pack(u, ARTIFACT_SUITCASE)
    s.commit(); s.close()
    txt="🧳 **Чемодан открыт!**\n"+"\n".join(f"{a.rarity_color} {a.name}" for a in arts)
    await cb.message.edit_text(txt, reply_markup=main_menu())
    await cb.answer()

@dp.callback_query(F.data=="menu_elite")
async def cb_elite(cb: CallbackQuery):
    s=SessionLocal()
    u=get_user(s, cb.from_user.id)
    if u.vip_level<ARTIFACT_ELITE["required_vip"]:
        await cb.answer("❌ Нужен VIP 5!", show_alert=True); s.close(); return
    if u.gems<ARTIFACT_ELITE["price_gems"]:
        await cb.answer("❌ Мало самоцветов!", show_alert=True); s.close(); return
    u.gems-=ARTIFACT_ELITE["price_gems"]
    arts=open_pack(u, ARTIFACT_ELITE)
    s.commit(); s.close()
    txt="👑 **Элитный кейс!**\n"+"\n".join(f"{a.rarity_color} {a.name}" for a in arts)
    await cb.message.edit_text(txt, reply_markup=main_menu())
    await cb.answer()

# Шахты
@dp.callback_query(F.data=="menu_arenas")
async def cb_arenas(cb: CallbackQuery):
    s=SessionLocal()
    u=get_user(s, cb.from_user.id)
    txt=f"⛏ Шахты (текущая: {u.arena}/50)\n\n"
    b=InlineKeyboardBuilder()
    for an, nm, _, _, _ in ARENAS:
        if an<=u.arena:
            b.button(text=f"✅ {an}", callback_data=f"arena_{an}")
        else:
            b.button(text=f"🔒 {an}", callback_data="locked")
    b.button(text="◀ Назад", callback_data="menu_main")
    b.adjust(5)
    s.close()
    await cb.message.edit_text(txt, reply_markup=b.as_markup())
    await cb.answer()

@dp.callback_query(F.data.startswith("arena_"))
async def cb_arena(cb: CallbackQuery):
    an=int(cb.data.split("_")[1])
    s=SessionLocal()
    u=get_user(s, cb.from_user.id)
    if an>u.arena: await cb.answer("❌ Закрыта!", show_alert=True); s.close(); return
    ar=s.query(Arena).filter(Arena.arena_number==an).first()
    bs=s.query(Boss).filter(Boss.arena_id==ar.id).all()
    b=InlineKeyboardBuilder()
    for boss in bs:
        b.button(text=f"⚔️ {boss.name}", callback_data=f"boss_{an}_{boss.boss_number}")
    b.button(text="◀ Назад", callback_data="menu_arenas")
    b.adjust(1)
    s.close()
    await cb.message.edit_text(f"⛏ {ar.name}\n{ar.description}\n💰 {ar.reward_coins} золота", reply_markup=b.as_markup())
    await cb.answer()

@dp.callback_query(F.data.startswith("boss_"))
async def cb_boss(cb: CallbackQuery):
    _, an, bn = cb.data.split("_")
    an, bn = int(an), int(bn)
    s=SessionLocal()
    u=get_user(s, cb.from_user.id)
    ar=s.query(Arena).filter(Arena.arena_number==an).first()
    boss=s.query(Boss).filter(Boss.arena_id==ar.id, Boss.boss_number==bn).first()
    update_stats(u)
    b=InlineKeyboardBuilder()
    b.button(text="⚔️ В БОЙ!", callback_data=f"fight_{an}_{bn}")
    b.button(text="◀ Назад", callback_data=f"arena_{an}")
    s.close()
    await cb.message.edit_text(f"👹 {boss.name}\n❤️ {boss.health} | ⚔️ {boss.damage}\n💰 {boss.reward_coins} золота\n\nТвоя сила: ⚔️ {u.damage}", reply_markup=b.as_markup())
    await cb.answer()

@dp.callback_query(F.data.startswith("fight_"))
async def cb_fight(cb: CallbackQuery, state: FSMContext):
    _, an, bn = cb.data.split("_")
    an, bn = int(an), int(bn)
    s=SessionLocal()
    u=get_user(s, cb.from_user.id)
    ar=s.query(Arena).filter(Arena.arena_number==an).first()
    boss=s.query(Boss).filter(Boss.arena_id==ar.id, Boss.boss_number==bn).first()
    update_stats(u)
    active_fights[cb.from_user.id] = {"an":an, "bn":bn, "uhp":u.max_health, "bhp":boss.health}
    await state.set_state(FightStates.in_fight)
    s.close()
    await cb.message.edit_text(f"⚔️ БОЙ!\n👹 {boss.name}\n❤️ {boss.health} | ⚔️ {boss.damage}\n\nТы: ❤️ {u.max_health} | ⚔️ {u.damage}", reply_markup=fight_kb(boss, an, bn))
    await cb.answer()

@dp.callback_query(F.data.startswith("atk_"), FightStates.in_fight)
async def cb_attack(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in active_fights:
        await cb.answer("Бой не найден!", show_alert=True); await state.clear(); return
    f=active_fights[cb.from_user.id]
    _, an, bn = cb.data.split("_")
    an, bn = int(an), int(bn)
    s=SessionLocal()
    u=get_user(s, cb.from_user.id)
    boss=s.query(Boss).filter(Boss.arena_id==s.query(Arena).filter(Arena.arena_number==an).first().id, Boss.boss_number==bn).first()
    update_stats(u)
    dmg=max(1, u.damage-boss.defense//2)
    if random.random()<u.critical_chance: dmg=int(dmg*u.critical_damage)
    f["bhp"]-=dmg
    if f["bhp"]<=0:
        u.coins+=boss.reward_coins; u.exp+=boss.reward_exp; u.gems+=boss.reward_gems
        if random.random()<boss.artifact_drop_chance:
            art=create_artifact(u.id)
            txt=f"🏆 Победа!\n💰 +{boss.reward_coins}\n💍 +{art.rarity_color} {art.name}!"
        else:
            txt=f"🏆 Победа!\n💰 +{boss.reward_coins}"
        if an==u.arena and an<50: u.arena+=1; txt+=f"\n⛏ Открыта шахта {u.arena}!"
        s.commit(); s.close()
        del active_fights[cb.from_user.id]; await state.clear()
        await cb.message.edit_text(txt, reply_markup=main_menu())
        await cb.answer("Победа!", show_alert=True)
        return
    bdmg=max(1, boss.damage-u.defense//2)
    f["uhp"]-=bdmg
    if f["uhp"]<=0:
        s.close(); del active_fights[cb.from_user.id]; await state.clear()
        await cb.message.edit_text("💀 Поражение!", reply_markup=main_menu())
        await cb.answer("Поражение!", show_alert=True)
        return
    s.close()
    await cb.message.edit_text(f"⚔️ Бой!\nТы нанёс {dmg}\n👹 HP: {f['bhp']}/{boss.health}\n❤️ Ты: {f['uhp']}/{u.max_health}", reply_markup=fight_kb(boss, an, bn))
    await cb.answer()

# Промокоды
@dp.callback_query(F.data=="menu_promo")
async def cb_promo(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🎟 Введите промокод:")
    await state.set_state(GameStates.waiting_for_promo_code)
    await cb.answer()

@dp.message(GameStates.waiting_for_promo_code)
async def promo_use(msg: Message, state: FSMContext):
    s=SessionLocal()
    p=s.query(PromoCode).filter(PromoCode.code==msg.text.upper(), PromoCode.is_active==True).first()
    if not p:
        await msg.answer("❌ Не найден!"); await state.clear(); s.close(); return
    if not p.is_permanent and p.expires_at and p.expires_at<datetime.now():
        await msg.answer("❌ Истек!"); await state.clear(); s.close(); return
    if p.uses_count>=p.uses_limit:
        await msg.answer("❌ Лимит!"); await state.clear(); s.close(); return
    u=get_user(s, msg.from_user.id)
    if s.query(PromoUsed).filter(PromoUsed.user_id==u.id, PromoUsed.promo_id==p.id).first():
        await msg.answer("❌ Уже использован!"); await state.clear(); s.close(); return
    u.coins+=p.reward_coins; u.gems+=p.reward_gems
    if p.reward_item: s.add(Inventory(user_id=u.id, item_type="special", item_name=p.reward_item, quantity=1))
    s.add(PromoUsed(user_id=u.id, promo_id=p.id))
    p.uses_count+=1; s.commit(); s.close()
    await msg.answer("✅ Промокод активирован!", reply_markup=main_menu())
    await state.clear()

# Магазин и помощь
@dp.callback_query(F.data=="menu_donate")
async def cb_donate(cb: CallbackQuery):
    await cb.message.edit_text("💎 Магазин\n\n👑 Статусы навсегда:\n⭐ Бывалый - 99₽\n🔥 Старатель - 299₽\n💎 Золотоискатель - 699₽\n✨ Хранитель - 1499₽\n👑 Властелин - 3499₽\n\n📝 @DEDACHAAVIVA", reply_markup=main_menu())
    await cb.answer()

@dp.callback_query(F.data=="menu_help")
async def cb_help(cb: CallbackQuery):
    await cb.message.edit_text("⛏ Помощь\n/menu - меню\n/profile - профиль\n🎒 Сумка - 5000💰\n🧳 Чемодан - 500💎\n👑 Элитный - 2000💎", reply_markup=main_menu())
    await cb.answer()

# Админ
@dp.message(Command("createpromo"))
async def create_promo(msg: Message):
    if not is_admin(msg.from_user.id): await msg.answer("⛔"); return
    p=msg.text.split()
    if len(p)<6: await msg.answer("Формат: /createpromo КОД МОНЕТЫ САМОЦВЕТЫ ЛИМИТ ДНИ|permanent"); return
    s=SessionLocal()
    perm=p[5].lower()=="permanent"
    exp=None if perm else datetime.now()+timedelta(days=int(p[5]))
    s.add(PromoCode(code=p[1].upper(), reward_coins=int(p[2]), reward_gems=int(p[3]), uses_limit=int(p[4]), expires_at=exp, is_permanent=perm, created_by=msg.from_user.id))
    s.commit(); s.close()
    await msg.answer(f"✅ Промокод {p[1].upper()} создан!")

# ==================== ЗАПУСК ====================

async def main():
    global bot
    init_db()
    print("✅ БД готова")
    session = AiohttpSession(timeout=60)
    bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode="HTML"))
    print("⛏ Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
