import asyncio
import logging
import json
import random
import os
from datetime import datetime, timedelta
from typing import Optional, List, Any, Dict

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
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
    raise ValueError("❌ Не указан BOT_TOKEN в переменных окружения!")

ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(",") if id.strip()] if ADMIN_IDS_STR else []
if not ADMIN_IDS:
    print("⚠️ ADMIN_IDS не настроены! Админ-команды не будут работать.")

# ==================== БАЗА ДАННЫХ ====================
DB_PATH = os.getenv("DB_PATH", "dark_mines.db")
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
    waiting_for_clan_name = State()
    waiting_for_transfer_artifact = State()
    waiting_for_trust_artifact = State()
    waiting_for_artifact_upgrade = State()
    waiting_for_promo_code = State()

# ==================== DP ====================
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
bot = None

# ==================== МОДЕЛИ ====================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, default="")
    first_name = Column(String, default="")
    last_name = Column(String, default="")
    title = Column(String, default="Начинающий шахтер")
    registered_at = Column(DateTime, default=datetime.now)
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
    
    clan_id = Column(Integer, ForeignKey("clans.id"), nullable=True)
    clan_role = Column(String, default="member")
    
    last_daily = Column(DateTime, nullable=True)
    daily_streak = Column(Integer, default=0)
    rebirth_count = Column(Integer, default=0)
    rebirth_multiplier = Column(Float, default=1.0)
    vip_set_received = Column(Boolean, default=False)
    
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(String, default="")
    banned_at = Column(DateTime, nullable=True)
    is_admin = Column(Boolean, default=False)
    notifications_enabled = Column(Boolean, default=True)
    saved_items = Column(Text, default="[]")
    
    clan = relationship("Clan", back_populates="members")
    inventory = relationship("Inventory", back_populates="user", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="owner", foreign_keys="Artifact.owner_id")
    promo_used = relationship("PromoUsed", back_populates="user")
    
    def get_saved_items(self):
        return json.loads(self.saved_items) if self.saved_items else []
    
    @property
    def is_vip(self):
        return self.vip_level > 0
    
    @property
    def vip_title(self):
        titles = {0: "Новичок", 1: "Бывалый шахтер", 2: "Старатель", 3: "Золотоискатель", 4: "Хранитель недр", 5: "Властелин шахт"}
        return titles.get(self.vip_level, "Легенда")


class Clan(Base):
    __tablename__ = "clans"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    tag = Column(String, unique=True, nullable=False)
    level = Column(Integer, default=1)
    exp = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    leader_id = Column(BigInteger, nullable=False)
    coins = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    
    members = relationship("User", back_populates="clan")
    
    @property
    def member_count(self):
        return len(self.members)


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
    created_at = Column(DateTime, default=datetime.now)
    
    owner = relationship("User", back_populates="artifacts", foreign_keys=[owner_id])
    trusted_to_user = relationship("User", foreign_keys=[trusted_to])
    
    @property
    def rarity_color(self):
        colors = {"common": "⬜", "rare": "🟦", "epic": "🟪", "legendary": "🟨", "mythical": "🟥"}
        return colors.get(self.rarity, "⬜")
    
    @property
    def rarity_name(self):
        names = {"common": "Обычный", "rare": "Редкий", "epic": "Эпический", "legendary": "Легендарный", "mythical": "Мифический"}
        return names.get(self.rarity, "Обычный")
    
    @property
    def type_name(self):
        names = {"ring": "💍 Кольцо", "amulet": "📿 Амулет", "stone": "💎 Камень", "scroll": "📜 Свиток", "crystal": "🔮 Кристалл", "rune": "ᚱ Руна"}
        return names.get(self.artifact_type, "Артефакт")


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
    special_drop = Column(String, nullable=True)
    special_drop_chance = Column(Float, default=0.05)
    artifact_drop_chance = Column(Float, default=0.1)
    
    arena = relationship("Arena")


class Case(Base):
    __tablename__ = "cases"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(String)
    price_coins = Column(Integer, default=0)
    price_gems = Column(Integer, default=0)
    required_vip = Column(Integer, default=0)
    drop_table = Column(Text)


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
    created_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


class PromoUsed(Base):
    __tablename__ = "promo_used"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    promo_id = Column(Integer, ForeignKey("promo_codes.id"))
    used_at = Column(DateTime, default=datetime.now)
    
    user = relationship("User", back_populates="promo_used")
    promo = relationship("PromoCode")


class AdminLog(Base):
    __tablename__ = "admin_logs"
    id = Column(Integer, primary_key=True)
    admin_id = Column(BigInteger, nullable=False)
    action = Column(String)
    target_id = Column(BigInteger, nullable=True)
    details = Column(Text)
    created_at = Column(DateTime, default=datetime.now)


# ==================== 60 АРТЕФАКТОВ ====================

ARTIFACTS = {
    "ring": [
        {"name": "Кольцо шахтера", "rarity": "common", "damage_bonus": 5, "defense_bonus": 3},
        {"name": "Кольцо удачи", "rarity": "rare", "crit_chance_bonus": 0.05, "coin_bonus": 0.1},
        {"name": "Кольцо вампира", "rarity": "epic", "lifesteal_bonus": 0.1, "damage_bonus": 15},
        {"name": "Кольцо невидимости", "rarity": "legendary", "dodge_bonus": 0.15, "defense_bonus": 20},
        {"name": "Кольцо всевластия", "rarity": "mythical", "damage_bonus": 50, "defense_bonus": 50, "health_bonus": 500, "crit_chance_bonus": 0.1},
        {"name": "Кольцо магмы", "rarity": "rare", "damage_bonus": 12, "crit_damage_bonus": 0.3},
        {"name": "Кольцо льда", "rarity": "rare", "defense_bonus": 15, "damage_reduction": 0.05},
        {"name": "Кольцо скорости", "rarity": "epic", "dodge_bonus": 0.1, "exp_bonus": 0.15},
        {"name": "Кольцо жадности", "rarity": "epic", "coin_bonus": 0.3, "damage_bonus": 8},
        {"name": "Кольцо бессмертия", "rarity": "legendary", "health_bonus": 300, "lifesteal_bonus": 0.15, "damage_reduction": 0.1},
    ],
    "amulet": [
        {"name": "Амулет здоровья", "rarity": "common", "health_bonus": 100},
        {"name": "Амулет силы", "rarity": "rare", "damage_bonus": 20, "health_bonus": 50},
        {"name": "Амулет защиты", "rarity": "rare", "defense_bonus": 25, "damage_reduction": 0.08},
        {"name": "Амулет критов", "rarity": "epic", "crit_chance_bonus": 0.12, "crit_damage_bonus": 0.5},
        {"name": "Амулет дракона", "rarity": "legendary", "damage_bonus": 35, "defense_bonus": 35, "health_bonus": 350, "crit_damage_bonus": 0.8},
        {"name": "Амулет тени", "rarity": "epic", "dodge_bonus": 0.12, "crit_chance_bonus": 0.08},
        {"name": "Амулет шахтера", "rarity": "common", "exp_bonus": 0.1, "coin_bonus": 0.1},
        {"name": "Амулет феникса", "rarity": "legendary", "health_bonus": 400, "lifesteal_bonus": 0.2, "damage_bonus": 25},
        {"name": "Амулет бездны", "rarity": "mythical", "damage_bonus": 60, "defense_bonus": 40, "crit_chance_bonus": 0.15, "crit_damage_bonus": 1.0, "dodge_bonus": 0.1},
        {"name": "Амулет времени", "rarity": "mythical", "exp_bonus": 0.5, "coin_bonus": 0.5, "health_bonus": 250, "damage_reduction": 0.15},
    ],
    "stone": [
        {"name": "Камень удачи", "rarity": "common", "coin_bonus": 0.15},
        {"name": "Камень опыта", "rarity": "rare", "exp_bonus": 0.25},
        {"name": "Рубин крови", "rarity": "epic", "lifesteal_bonus": 0.12, "damage_bonus": 18},
        {"name": "Сапфир магии", "rarity": "epic", "defense_bonus": 30, "damage_reduction": 0.1},
        {"name": "Алмаз чистоты", "rarity": "legendary", "damage_bonus": 40, "defense_bonus": 30, "health_bonus": 200, "crit_chance_bonus": 0.08},
        {"name": "Изумруд жизни", "rarity": "rare", "health_bonus": 200, "lifesteal_bonus": 0.05},
        {"name": "Топаз скорости", "rarity": "rare", "dodge_bonus": 0.08, "exp_bonus": 0.1},
        {"name": "Аметист тени", "rarity": "epic", "dodge_bonus": 0.15, "crit_chance_bonus": 0.1},
        {"name": "Черный бриллиант", "rarity": "legendary", "damage_bonus": 50, "crit_damage_bonus": 0.7, "lifesteal_bonus": 0.1},
        {"name": "Камень мироздания", "rarity": "mythical", "damage_bonus": 70, "defense_bonus": 70, "health_bonus": 700, "crit_chance_bonus": 0.15, "crit_damage_bonus": 1.0, "dodge_bonus": 0.15, "lifesteal_bonus": 0.15, "exp_bonus": 0.3, "coin_bonus": 0.3},
    ],
    "scroll": [
        {"name": "Свиток мудрости", "rarity": "common", "exp_bonus": 0.2},
        {"name": "Свиток богатства", "rarity": "rare", "coin_bonus": 0.25, "exp_bonus": 0.1},
        {"name": "Свиток войны", "rarity": "epic", "damage_bonus": 25, "crit_damage_bonus": 0.4},
        {"name": "Свиток защиты", "rarity": "rare", "defense_bonus": 20, "damage_reduction": 0.05},
        {"name": "Свиток вампира", "rarity": "epic", "lifesteal_bonus": 0.15, "health_bonus": 150},
        {"name": "Свиток скорости", "rarity": "rare", "dodge_bonus": 0.1, "crit_chance_bonus": 0.05},
        {"name": "Свиток баланса", "rarity": "legendary", "damage_bonus": 30, "defense_bonus": 30, "health_bonus": 300, "crit_chance_bonus": 0.05, "dodge_bonus": 0.05},
        {"name": "Свиток дракона", "rarity": "legendary", "damage_bonus": 45, "crit_damage_bonus": 0.6, "health_bonus": 200},
        {"name": "Свиток бога", "rarity": "mythical", "damage_bonus": 55, "defense_bonus": 55, "health_bonus": 550, "crit_chance_bonus": 0.1, "crit_damage_bonus": 0.8, "exp_bonus": 0.4},
        {"name": "Свиток пустоты", "rarity": "mythical", "damage_bonus": 65, "lifesteal_bonus": 0.2, "dodge_bonus": 0.12, "damage_reduction": 0.12},
    ],
    "crystal": [
        {"name": "Кристалл маны", "rarity": "common", "health_bonus": 80},
        {"name": "Кристалл силы", "rarity": "rare", "damage_bonus": 15, "crit_damage_bonus": 0.2},
        {"name": "Кристалл защиты", "rarity": "rare", "defense_bonus": 18, "damage_reduction": 0.05},
        {"name": "Кристалл жизни", "rarity": "epic", "health_bonus": 250, "lifesteal_bonus": 0.08},
        {"name": "Кристалл удачи", "rarity": "epic", "crit_chance_bonus": 0.1, "coin_bonus": 0.2},
        {"name": "Кристалл скорости", "rarity": "rare", "dodge_bonus": 0.08, "exp_bonus": 0.15},
        {"name": "Кристалл тени", "rarity": "epic", "dodge_bonus": 0.12, "crit_chance_bonus": 0.08, "damage_bonus": 10},
        {"name": "Кристалл звезды", "rarity": "legendary", "damage_bonus": 35, "defense_bonus": 35, "health_bonus": 350, "crit_chance_bonus": 0.08},
        {"name": "Кристалл бездны", "rarity": "legendary", "damage_bonus": 50, "crit_damage_bonus": 0.5, "lifesteal_bonus": 0.12},
        {"name": "Кристалл творца", "rarity": "mythical", "damage_bonus": 60, "defense_bonus": 60, "health_bonus": 600, "crit_chance_bonus": 0.12, "crit_damage_bonus": 0.9, "lifesteal_bonus": 0.12, "exp_bonus": 0.3},
    ],
    "rune": [
        {"name": "Руна огня", "rarity": "common", "damage_bonus": 8},
        {"name": "Руна льда", "rarity": "common", "defense_bonus": 8},
        {"name": "Руна жизни", "rarity": "rare", "health_bonus": 150, "lifesteal_bonus": 0.05},
        {"name": "Руна смерти", "rarity": "epic", "damage_bonus": 20, "crit_damage_bonus": 0.3, "lifesteal_bonus": 0.1},
        {"name": "Руна скорости", "rarity": "rare", "dodge_bonus": 0.1, "exp_bonus": 0.1},
        {"name": "Руна богатства", "rarity": "rare", "coin_bonus": 0.2},
        {"name": "Руна защиты", "rarity": "epic", "defense_bonus": 25, "damage_reduction": 0.08, "health_bonus": 100},
        {"name": "Руна дракона", "rarity": "legendary", "damage_bonus": 40, "crit_chance_bonus": 0.08, "crit_damage_bonus": 0.5},
        {"name": "Руна судьбы", "rarity": "legendary", "crit_chance_bonus": 0.12, "crit_damage_bonus": 0.6, "coin_bonus": 0.25, "exp_bonus": 0.25},
        {"name": "Руна бога", "rarity": "mythical", "damage_bonus": 50, "defense_bonus": 50, "health_bonus": 500, "crit_chance_bonus": 0.1, "crit_damage_bonus": 0.7, "dodge_bonus": 0.1, "lifesteal_bonus": 0.1, "damage_reduction": 0.1},
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
    (1, "🏔 Заброшенная штольня", "Старая выработка у подножия гор", 100, 50),
    (2, "🔥 Огненный карьер", "Глубокий разрез с лавовыми озерами", 150, 75),
    (3, "❄ Мерзлая пещера", "Ледяные гроты вечной зимы", 200, 100),
    (4, "🌲 Таежный прииск", "Золотоносные жилы в глухом лесу", 250, 125),
    (5, "⚡ Грозовой разлом", "Ущелье где бьют молнии", 300, 150),
    (6, "💀 Костяной карьер", "Древнее кладбище динозавров", 350, 175),
    (7, "🏜 Песчаный рудник", "Золотые пески пустыни", 400, 200),
    (8, "🌋 Жерло вулкана", "Действующий вулкан с магмой", 450, 225),
    (9, "🌊 Затопленная шахта", "Подземные воды и сокровища", 500, 250),
    (10, "🏰 Каменоломня великанов", "Следы древней цивилизации", 550, 275),
    (11, "🌀 Искривленная жила", "Аномальная зона добычи", 600, 300),
    (12, "✨ Звездная пещера", "Метеоритное железо", 650, 325),
    (13, "💎 Алмазный карьер", "Кимберлитовая трубка", 700, 350),
    (14, "🦴 Драконий кряж", "Окаменелые останки драконов", 750, 375),
    (15, "👁 Око бездны", "Бездонная шахта", 800, 400),
    (16, "🌑 Мрачная расщелина", "Царство вечной тьмы", 850, 425),
    (17, "⚙ Механический цех", "Заброшенный завод гномов", 900, 450),
    (18, "🌈 Радужный карьер", "Опаловые жилы", 950, 475),
    (19, "👑 Королевская шахта", "Золото императоров", 1000, 500),
    (20, "🌟 Астральный разлом", "Месторождение редчайших руд", 1050, 525),
    (21, "🕳 Черная дыра", "Гравитационная аномалия", 1100, 550),
    (22, "🧊 Ледник титанов", "Замерзшие гиганты", 1150, 575),
    (23, "🌪 Ураганный карьер", "Вечный шторм", 1200, 600),
    (24, "🐉 Логово дракона", "Гнездо древнего змея", 1250, 625),
    (25, "🔮 Хрустальный грот", "Магические кристаллы", 1300, 650),
    (26, "🕸 Паучья пещера", "Сети Арахнида", 1350, 675),
    (27, "🌌 Космическая жила", "Руда с астероидов", 1400, 700),
    (28, "🧟 Проклятый рудник", "Шахта нежити", 1450, 725),
    (29, "🔱 Подводный карьер", "Затопленный город", 1500, 750),
    (30, "⛓ Цепи Тартара", "Врата в преисподнюю", 1550, 775),
    (31, "🦑 Бездна Кракена", "Логово морского чудовища", 1600, 800),
    (32, "🌵 Кактусовый каньон", "Высохшее море", 1650, 825),
    (33, "🎭 Маскарад теней", "Иллюзорная шахта", 1700, 850),
    (34, "⚰ Склеп фараона", "Проклятая гробница", 1750, 875),
    (35, "🦅 Орлиное гнездо", "Заоблачный пик", 1800, 900),
    (36, "🧊 Нулевой карьер", "Абсолютный ноль", 1850, 925),
    (37, "🌋 Магмовый колодец", "Ядро планеты", 1900, 950),
    (38, "🦂 Скорпионья нора", "Ядовитые пески", 1950, 975),
    (39, "🎪 Цирк уродов", "Безумная шахта", 2000, 1000),
    (40, "🏛 Храм забвения", "Руины богов", 2050, 1025),
    (41, "🌠 Падающая звезда", "Упавший метеорит", 2100, 1050),
    (42, "🧬 Мутагенная жила", "Радиоактивная руда", 2150, 1075),
    (43, "👹 Демонический разлом", "Врата ада", 2200, 1100),
    (44, "🦋 Сад каменных бабочек", "Окаменелый лес", 2250, 1125),
    (45, "⚗ Алхимический цех", "Философский камень", 2300, 1150),
    (46, "🗿 Истуканы острова", "Гигантские статуи", 2350, 1175),
    (47, "🕰 Часовой механизм", "Остановленное время", 2400, 1200),
    (48, "🎭 Театр марионеток", "Кукольный дом", 2450, 1225),
    (49, "👻 Призрачный рудник", "Шахта духов", 2500, 1250),
    (50, "👑 Тронный зал глубин", "Последняя шахта", 3000, 1500),
]

BOSSES = {}
for arena_num, _, _, _, _ in ARENAS:
    if arena_num == 1:
        BOSSES[1] = [
            ("Крот-мутант", "Подземный вредитель", 150, 25, 5, 200, 80, "Железная руда", 0.5, None, 0, 0.05),
            ("Каменный голем", "Страж штольни", 250, 35, 8, 300, 100, "Медная руда", 0.4, None, 0, 0.07),
            ("Теневой шахтер", "Проклятый рудокоп", 350, 45, 10, 400, 120, "Серебряная руда", 0.6, "⭐ Кольцо шахтера", 0.05, 0.1),
        ]
    elif arena_num == 2:
        BOSSES[2] = [
            ("Лавовый элементаль", "Дитя магмы", 400, 55, 12, 500, 150, "Огненный кристалл", 0.5, "🔥 Сердце вулкана", 0.1, 0.08),
            ("Огненная саламандра", "Хозяйка карьера", 500, 65, 15, 600, 180, "Чешуя саламандры", 0.5, None, 0, 0.09),
            ("Магматический гигант", "Пробужденный вулкан", 700, 80, 20, 800, 220, "Ядро магмы", 0.4, None, 0, 0.12),
        ]
    else:
        BOSSES[arena_num] = [
            (f"Хранитель недр {arena_num}", "Страж глубин", 500 + arena_num * 80, 60 + arena_num * 5, 15 + arena_num // 3, 400 + arena_num * 40, 150 + arena_num * 20, f"Редкая руда {arena_num}", 0.4, None, 0, 0.05 + (arena_num * 0.005)),
            (f"Темный старатель {arena_num}", "Проклятый золотоискатель", 700 + arena_num * 100, 80 + arena_num * 6, 20 + arena_num // 2, 600 + arena_num * 50, 200 + arena_num * 25, "Темный слиток", 0.35, None, 0, 0.06 + (arena_num * 0.005)),
            (f"Владыка шахт {arena_num}", "Повелитель рудников", 1000 + arena_num * 150, 120 + arena_num * 8, 30 + arena_num * 2, 900 + arena_num * 60, 300 + arena_num * 35, "Золотой самородок", 0.3, f"⭐ Ключ от сокровищницы {arena_num}", 0.05, 0.1 + (arena_num * 0.005)),
        ]

# ==================== СУМКИ С АРТЕФАКТАМИ ====================

ARTIFACT_BAG = {
    "name": "🎒 Сумка с артефактами",
    "description": "1 случайный артефакт",
    "price_coins": 5000,
    "price_gems": 100,
    "required_vip": 0,
    "artifact_count": 1,
    "rarity_weights": {"common": 0.50, "rare": 0.30, "epic": 0.15, "legendary": 0.04, "mythical": 0.01}
}

ARTIFACT_SUITCASE = {
    "name": "🧳 Чемодан с артефактами",
    "description": "3 случайных артефакта",
    "price_coins": 0,
    "price_gems": 500,
    "required_vip": 2,
    "artifact_count": 3,
    "rarity_weights": {"common": 0.20, "rare": 0.35, "epic": 0.25, "legendary": 0.15, "mythical": 0.05}
}

ARTIFACT_ELITE = {
    "name": "👑 Элитный кейс артефактов",
    "description": "5 артефактов",
    "price_coins": 0,
    "price_gems": 2000,
    "required_vip": 5,
    "artifact_count": 5,
    "rarity_weights": {"common": 0.05, "rare": 0.15, "epic": 0.25, "legendary": 0.35, "mythical": 0.20}
}

CASES = [
    {"name": "🎒 Снаряжение шахтера", "description": "Базовый набор", "price_coins": 1000, "price_gems": 0, "required_vip": 0, "items": [("Каска шахтера", 0.3), ("Спецовка", 0.3), ("500 золотых", 0.4)]},
    {"name": "💎 Самоцветы", "description": "Сундук с драгоценностями", "price_coins": 0, "price_gems": 100, "required_vip": 1, "items": [("✨ Сапфировая кирка", 0.2), ("✨ Рубиновая броня", 0.2), ("1000 золотых", 0.3), ("50 самоцветов", 0.2), ("🎴 Карта сокровищ", 0.1)]},
    {"name": "👑 Сундук старателя", "description": "Для опытных", "price_coins": 0, "price_gems": 500, "required_vip": 3, "items": [("⚡ Алмазная кирка", 0.15), ("🛡 Щит рудокопа", 0.15), ("5000 золотых", 0.25), ("200 самоцветов", 0.25), ("🐉 Яйцо шахтного дракона", 0.1)]},
    {"name": "🌟 Легендарный сундук", "description": "Для Властелинов шахт", "price_coins": 0, "price_gems": 1500, "required_vip": 5, "items": [("⚔️ Кирка титанов", 0.1), ("🛡 Нагрудник горняка", 0.1), ("👑 Титул Король шахт", 0.05), ("🐲 Древний шахтный дракон", 0.05), ("10000 золотых", 0.3), ("500 самоцветов", 0.3)]},
]

# ==================== ФУНКЦИИ ====================

def init_db():
    Base.metadata.create_all(engine)
    session = SessionLocal()
    
    for arena_num, name, desc, coins, exp in ARENAS:
        if not session.query(Arena).filter(Arena.arena_number == arena_num).first():
            session.add(Arena(arena_number=arena_num, name=name, description=desc, reward_coins=coins, reward_exp=exp))
    session.commit()
    
    for arena_num, bosses in BOSSES.items():
        arena = session.query(Arena).filter(Arena.arena_number == arena_num).first()
        if arena:
            for idx, bd in enumerate(bosses, 1):
                if not session.query(Boss).filter(Boss.arena_id == arena.id, Boss.boss_number == idx).first():
                    session.add(Boss(
                        arena_id=arena.id, boss_number=idx,
                        name=bd[0], title=bd[1], health=bd[2], damage=bd[3], defense=bd[4],
                        reward_coins=bd[5], reward_exp=bd[6], drop_material=bd[7], drop_chance=bd[8],
                        special_drop=bd[9] if len(bd) > 9 else None,
                        special_drop_chance=bd[10] if len(bd) > 10 else 0.05,
                        artifact_drop_chance=bd[11] if len(bd) > 11 else 0.1
                    ))
    
    for cd in CASES:
        if not session.query(Case).filter(Case.name == cd["name"]).first():
            session.add(Case(name=cd["name"], description=cd["description"], price_coins=cd["price_coins"], price_gems=cd["price_gems"], required_vip=cd["required_vip"], drop_table=json.dumps(cd["items"])))
    
    session.commit()
    session.close()
    print("✅ База данных готова")
    print(f"⛏ Шахт: {len(ARENAS)}, Боссов: {sum(len(b) for b in BOSSES.values())}")


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def get_user(session: Session, tg_id: int, create_if_not_exists: bool = True):
    user = session.query(User).filter(User.user_id == tg_id).first()
    if not user and create_if_not_exists:
        user = User(user_id=tg_id)
        session.add(user)
        session.commit()
        starter_items = [
            Inventory(item_type="weapon", item_name="Кирка новичка", quantity=1, equipped=True),
            Inventory(item_type="armor", item_name="Роба шахтера", quantity=1, equipped=True),
            Inventory(item_type="material", item_name="Пайка шахтера", quantity=5),
        ]
        for item in starter_items:
            item.user_id = user.id
            session.add(item)
        session.commit()
    return user


def update_user_stats(user: User):
    base_damage = 10 + (user.pickaxe_level - 1) * 4 + (user.rebirth_count * 8)
    base_defense = 5 + (user.armor_level - 1) * 3 + (user.helmet_level - 1) * 2 + (user.boots_level - 1) * 1 + (user.rebirth_count * 4)
    base_health = 100 + (user.armor_level - 1) * 15 + (user.helmet_level - 1) * 10 + (user.rebirth_count * 25)
    
    crit_chance = 0.1
    crit_damage = 2.0
    dodge_chance = 0.05
    lifesteal = 0.0
    
    session = SessionLocal()
    try:
        equipped = session.query(Artifact).filter(Artifact.owner_id == user.id, Artifact.equipped_slot > 0).all()
        for a in equipped:
            base_damage += a.damage_bonus
            base_defense += a.defense_bonus
            base_health += a.health_bonus
            crit_chance += a.crit_chance_bonus
            crit_damage += a.crit_damage_bonus
            dodge_chance += a.dodge_bonus
            lifesteal += a.lifesteal_bonus
    finally:
        session.close()
    
    if user.is_vip:
        mult = {1: 1.1, 2: 1.2, 3: 1.35, 4: 1.5, 5: 2.0}.get(user.vip_level, 1.0)
        base_damage = int(base_damage * mult)
        base_defense = int(base_defense * mult)
        base_health = int(base_health * mult)
        crit_chance += 0.05 + (user.vip_level * 0.03)
        crit_damage += 0.2 + (user.vip_level * 0.2)
        dodge_chance += 0.05 + (user.vip_level * 0.02)
        lifesteal += 0.05 * user.vip_level
    
    user.damage = base_damage
    user.defense = base_defense
    user.max_health = base_health
    user.critical_chance = min(crit_chance, 0.8)
    user.critical_damage = min(crit_damage, 5.0)
    user.dodge_chance = min(dodge_chance, 0.5)
    user.lifesteal = min(lifesteal, 0.5)
    user.max_energy = 100 + (user.lantern_level - 1) * 20


def create_random_artifact(owner_id: int, rarity_weights: dict = None) -> Artifact:
    if rarity_weights is None:
        rarity_weights = {"common": 0.5, "rare": 0.3, "epic": 0.13, "legendary": 0.05, "mythical": 0.02}
    
    session = SessionLocal()
    try:
        rarity = random.choices(list(rarity_weights.keys()), weights=list(rarity_weights.values()))[0]
        artifact_type = random.choice(list(ARTIFACTS.keys()))
        available = [a for a in ARTIFACTS[artifact_type] if a["rarity"] == rarity]
        if not available:
            available = [a for a in ARTIFACTS[artifact_type]]
        
        template = random.choice(available)
        artifact = Artifact(
            owner_id=owner_id, name=template["name"],
            artifact_type=artifact_type, rarity=rarity,
            damage_bonus=template.get("damage_bonus", 0),
            defense_bonus=template.get("defense_bonus", 0),
            health_bonus=template.get("health_bonus", 0),
            crit_chance_bonus=template.get("crit_chance_bonus", 0.0),
            crit_damage_bonus=template.get("crit_damage_bonus", 0.0),
            dodge_bonus=template.get("dodge_bonus", 0.0),
            lifesteal_bonus=template.get("lifesteal_bonus", 0.0),
            exp_bonus=template.get("exp_bonus", 0.0),
            coin_bonus=template.get("coin_bonus", 0.0),
            damage_reduction=template.get("damage_reduction", 0.0),
        )
        session.add(artifact)
        session.commit()
        session.refresh(artifact)
        return artifact
    finally:
        session.close()


def open_artifact_pack(user: User, pack_config: dict) -> list:
    artifacts = []
    for _ in range(pack_config["artifact_count"]):
        artifact = create_random_artifact(user.id, pack_config["rarity_weights"])
        artifacts.append(artifact)
    return artifacts


def get_profile_text(user: User, session: Session) -> str:
    update_user_stats(user)
    clan_name = user.clan.name if user.clan else "Нет гильдии"
    vip_status = f"{user.vip_title} (ур.{user.vip_level})"
    
    return f"""
⛏ **Профиль шахтера** - {user.title or user.first_name or user.username}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 **Основное**
├ ID: {user.user_id}
├ 🏅 Статус: {vip_status}
├ 🏰 Гильдия: {clan_name}
└ 🔄 Перерождений: {user.rebirth_count} (x{user.rebirth_multiplier:.1f})

⚔️ **Характеристики**
├ ❤️ Здоровье: {user.health}/{user.max_health}
├ ⚡ Энергия: {user.energy}/{user.max_energy}
├ ⚔️ Урон: {user.damage}
├ 🛡 Защита: {user.defense}
├ ✨ Крит. шанс: {int(user.critical_chance * 100)}%
├ 💥 Крит. урон: {int(user.critical_damage * 100)}%
├ 🏃 Уклонение: {int(user.dodge_chance * 100)}%
└ 🩸 Вампиризм: {int(user.lifesteal * 100)}%

💰 **Ресурсы**
├ 💰 Золото: {user.coins}
├ 💎 Самоцветы: {user.gems}
└ ✨ Опыт: {user.exp}

🏟 **Прогресс**
└ Шахта: {user.arena}/50
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


def main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🏟 Шахты", callback_data="menu_arenas")
    builder.button(text="👤 Профиль", callback_data="menu_profile")
    builder.button(text="🎒 Сумка артефактов", callback_data="menu_artifact_bag")
    builder.button(text="🧳 Чемодан артефактов", callback_data="menu_artifact_suitcase")
    builder.button(text="👑 Элитный кейс", callback_data="menu_artifact_elite")
    builder.button(text="🎟 Промокод", callback_data="menu_promo")
    builder.button(text="💎 Магазин", callback_data="menu_donate")
    builder.button(text="❓ Помощь", callback_data="menu_help")
    builder.adjust(2)
    return builder.as_markup()


# ==================== MIDDLEWARE ====================

@dp.message.middleware()
async def check_ban_middleware(handler, event: Message, data: dict):
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.user_id == event.from_user.id).first()
        if user and user.is_banned:
            await event.answer(f"⛔ Вы забанены!\nПричина: {user.ban_reason}")
            return
        return await handler(event, data)
    finally:
        session.close()


# ==================== ОСНОВНЫЕ ХЭНДЛЕРЫ ====================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    session = SessionLocal()
    try:
        user = get_user(session, message.from_user.id)
        user.last_active = datetime.now()
        user.first_name = message.from_user.first_name or ""
        user.last_name = message.from_user.last_name or ""
        user.username = message.from_user.username or ""
        session.commit()
        
        await message.answer(
            "⛏ **ТЕМНЫЕ ШАХТЫ** ⛏\n\n"
            "Добро пожаловать, шахтер!\n"
            "🏟 50 шахт | 💍 60 артефактов\n"
            "🎒 Сумки с артефактами\n"
            "🎟 Перманентные промокоды\n\n"
            "/menu - Главное меню\n"
            "/profile - Профиль\n"
            "/help - Помощь",
            reply_markup=main_menu_keyboard()
        )
    finally:
        session.close()


@dp.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer("⛏ **Главное меню**", reply_markup=main_menu_keyboard())


@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    session = SessionLocal()
    try:
        user = get_user(session, message.from_user.id)
        update_user_stats(user)
        session.commit()
        builder = InlineKeyboardBuilder()
        builder.button(text="◀ Назад", callback_data="menu_main")
        await message.answer(get_profile_text(user, session), parse_mode="Markdown", reply_markup=builder.as_markup())
    finally:
        session.close()


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "⛏ **Помощь**\n\n"
        "/menu - Меню\n"
        "/profile - Профиль\n"
        "/createpromo - Создать промокод (админ)\n"
        "/promolist - Список промокодов (админ)\n\n"
        "🎒 Сумка артефактов - 5000💰\n"
        "🧳 Чемодан артефактов - 500💎 (VIP 2+)\n"
        "👑 Элитный кейс - 2000💎 (VIP 5)"
    )


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Отменено", reply_markup=main_menu_keyboard())


# ==================== ГЛАВНОЕ МЕНЮ ====================

@dp.callback_query(F.data == "menu_main")
async def menu_main_callback(callback: CallbackQuery):
    await callback.message.edit_text("⛏ **Главное меню**", reply_markup=main_menu_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "menu_profile")
async def menu_profile_callback(callback: CallbackQuery):
    session = SessionLocal()
    try:
        user = get_user(session, callback.from_user.id)
        update_user_stats(user)
        session.commit()
        builder = InlineKeyboardBuilder()
        builder.button(text="◀ Назад", callback_data="menu_main")
        await callback.message.edit_text(get_profile_text(user, session), parse_mode="Markdown", reply_markup=builder.as_markup())
    finally:
        session.close()
    await callback.answer()


# ==================== СУМКИ С АРТЕФАКТАМИ ====================

@dp.callback_query(F.data == "menu_artifact_bag")
async def artifact_bag_callback(callback: CallbackQuery):
    session = SessionLocal()
    try:
        user = get_user(session, callback.from_user.id)
        
        if user.vip_level < ARTIFACT_BAG["required_vip"]:
            await callback.answer("❌ Недостаточный VIP!", show_alert=True)
            return
        
        if user.coins < ARTIFACT_BAG["price_coins"]:
            await callback.answer(f"❌ Нужно {ARTIFACT_BAG['price_coins']} золота!", show_alert=True)
            return
        
        user.coins -= ARTIFACT_BAG["price_coins"]
        artifacts = open_artifact_pack(user, ARTIFACT_BAG)
        session.commit()
        
        text = f"🎒 **Сумка открыта!**\n\n"
        for art in artifacts:
            text += f"{art.rarity_color} {art.name} ({art.rarity_name})\n"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🎒 Открыть еще", callback_data="menu_artifact_bag")
        builder.button(text="◀ Назад", callback_data="menu_main")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    finally:
        session.close()
    await callback.answer()


@dp.callback_query(F.data == "menu_artifact_suitcase")
async def artifact_suitcase_callback(callback: CallbackQuery):
    session = SessionLocal()
    try:
        user = get_user(session, callback.from_user.id)
        
        if user.vip_level < ARTIFACT_SUITCASE["required_vip"]:
            await callback.answer(f"❌ Нужен VIP {ARTIFACT_SUITCASE['required_vip']}!", show_alert=True)
            return
        
        if user.gems < ARTIFACT_SUITCASE["price_gems"]:
            await callback.answer(f"❌ Нужно {ARTIFACT_SUITCASE['price_gems']} самоцветов!", show_alert=True)
            return
        
        user.gems -= ARTIFACT_SUITCASE["price_gems"]
        artifacts = open_artifact_pack(user, ARTIFACT_SUITCASE)
        session.commit()
        
        text = f"🧳 **Чемодан открыт!**\n\n"
        for art in artifacts:
            text += f"{art.rarity_color} {art.name} ({art.rarity_name})\n"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🧳 Открыть еще", callback_data="menu_artifact_suitcase")
        builder.button(text="◀ Назад", callback_data="menu_main")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    finally:
        session.close()
    await callback.answer()


@dp.callback_query(F.data == "menu_artifact_elite")
async def artifact_elite_callback(callback: CallbackQuery):
    session = SessionLocal()
    try:
        user = get_user(session, callback.from_user.id)
        
        if user.vip_level < ARTIFACT_ELITE["required_vip"]:
            await callback.answer(f"❌ Нужен VIP {ARTIFACT_ELITE['required_vip']}!", show_alert=True)
            return
        
        if user.gems < ARTIFACT_ELITE["price_gems"]:
            await callback.answer(f"❌ Нужно {ARTIFACT_ELITE['price_gems']} самоцветов!", show_alert=True)
            return
        
        user.gems -= ARTIFACT_ELITE["price_gems"]
        artifacts = open_artifact_pack(user, ARTIFACT_ELITE)
        session.commit()
        
        text = f"👑 **Элитный кейс открыт!**\n\n"
        for art in artifacts:
            text += f"{art.rarity_color} {art.name} ({art.rarity_name})\n"
        
        builder = InlineKeyboardBuilder()
        builder.button(text="👑 Открыть еще", callback_data="menu_artifact_elite")
        builder.button(text="◀ Назад", callback_data="menu_main")
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    finally:
        session.close()
    await callback.answer()


# ==================== ПРОМОКОДЫ ====================

@dp.message(Command("createpromo"))
async def cmd_create_promo(message: Message):
    session = SessionLocal()
    try:
        if not is_admin(message.from_user.id):
            await message.answer("⛔ Доступ запрещен!")
            return
        
        parts = message.text.split()
        if len(parts) < 6:
            await message.answer(
                "❌ Формат: /createpromo КОД МОНЕТЫ САМОЦВЕТЫ ЛИМИТ ДНИ|permanent [ПРЕДМЕТ]\n\n"
                "Примеры:\n"
                "/createpromo TEST 1000 100 50 30\n"
                "/createpromo GOLD 5000 500 100 permanent\n"
                "/createpromo GIFT 0 100 10 7 Алмазная_кирка"
            )
            return
        
        code = parts[1].upper()
        coins = int(parts[2])
        gems = int(parts[3])
        uses_limit = int(parts[4])
        duration = parts[5]
        
        is_permanent = duration.lower() == "permanent"
        expires_at = None if is_permanent else datetime.now() + timedelta(days=int(duration))
        reward_item = " ".join(parts[6:]) if len(parts) > 6 else None
        
        if session.query(PromoCode).filter(PromoCode.code == code).first():
            await message.answer(f"❌ Код {code} уже существует!")
            return
        
        promo = PromoCode(
            code=code, reward_coins=coins, reward_gems=gems,
            reward_item=reward_item, uses_limit=uses_limit,
            expires_at=expires_at, is_permanent=is_permanent,
            created_by=message.from_user.id
        )
        session.add(promo)
        session.commit()
        
        dtype = "перманентный ♾️" if is_permanent else f"на {duration} дн."
        await message.answer(f"✅ Промокод {code} создан!\nТип: {dtype}\n💰{coins} 💎{gems} 👥{uses_limit}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        session.close()


@dp.message(Command("promolist"))
async def cmd_promo_list(message: Message):
    session = SessionLocal()
    try:
        if not is_admin(message.from_user.id):
            await message.answer("⛔ Доступ запрещен!")
            return
        
        promos = session.query(PromoCode).order_by(PromoCode.created_at.desc()).limit(10).all()
        if not promos:
            await message.answer("Нет промокодов.")
            return
        
        text = "📝 **Промокоды:**\n\n"
        for p in promos:
            pt = "♾️" if p.is_permanent else "📅"
            text += f"{pt} {p.code} | {p.uses_count}/{p.uses_limit}\n"
        
        await message.answer(text)
    finally:
        session.close()


@dp.callback_query(F.data == "menu_promo")
async def menu_promo_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🎟 Введите промокод:")
    await state.set_state(GameStates.waiting_for_promo_code)
    await callback.answer()


@dp.message(GameStates.waiting_for_promo_code)
async def process_promo_code(message: Message, state: FSMContext):
    session = SessionLocal()
    try:
        promo = session.query(PromoCode).filter(
            PromoCode.code == message.text.upper(),
            PromoCode.is_active == True
        ).first()
        
        if not promo:
            await message.answer("❌ Не найден!")
            await state.clear()
            return
        
        if not promo.is_permanent and promo.expires_at and promo.expires_at < datetime.now():
            await message.answer("❌ Истек!")
            await state.clear()
            return
        
        if promo.uses_count >= promo.uses_limit:
            await message.answer("❌ Лимит исчерпан!")
            await state.clear()
            return
        
        user = get_user(session, message.from_user.id)
        
        if session.query(PromoUsed).filter(PromoUsed.user_id == user.id, PromoUsed.promo_id == promo.id).first():
            await message.answer("❌ Уже использован!")
            await state.clear()
            return
        
        user.coins += promo.reward_coins
        user.gems += promo.reward_gems
        
        if promo.reward_item:
            session.add(Inventory(user_id=user.id, item_type="special", item_name=promo.reward_item, quantity=1))
        
        session.add(PromoUsed(user_id=user.id, promo_id=promo.id))
        promo.uses_count += 1
        session.commit()
        
        text = "✅ Активирован!\n"
        if promo.reward_coins: text += f"💰 +{promo.reward_coins}\n"
        if promo.reward_gems: text += f"💎 +{promo.reward_gems}\n"
        if promo.reward_item: text += f"🎁 +{promo.reward_item}\n"
        
        await message.answer(text, reply_markup=main_menu_keyboard())
        await state.clear()
    finally:
        session.close()


# ==================== МАГАЗИН ====================

@dp.callback_query(F.data == "menu_donate")
async def donate_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "💎 **Магазин**\n\n"
        "👑 Статусы (навсегда):\n"
        "⭐ Бывалый - 99₽\n"
        "🔥 Старатель - 299₽\n"
        "💎 Золотоискатель - 699₽\n"
        "✨ Хранитель недр - 1499₽\n"
        "👑 Властелин шахт - 3499₽\n\n"
        "💎 Самоцветы: от 49₽\n\n"
        "📝 @DEDACHAAVIVA",
        reply_markup=InlineKeyboardBuilder()
            .button(text="💎 Купить", url="https://t.me/DEDACHAAVIVA")
            .button(text="◀ Назад", callback_data="menu_main")
            .adjust(1)
            .as_markup(),
        disable_web_page_preview=True
    )
    await callback.answer()


@dp.callback_query(F.data == "menu_help")
async def menu_help_callback(callback: CallbackQuery):
    await cmd_help(callback.message)
    await callback.answer()


# ==================== ЗАПУСК ====================

async def main():
    global bot
    init_db()
    
    session = AiohttpSession(timeout=60)
    bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode="HTML"))
    
    print("⛏ ТЕМНЫЕ ШАХТЫ БОТ ЗАПУЩЕН")
    print(f"⛏ Шахт: 50 | 👹 Боссов: 150 | 💍 Артефактов: 60")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Бот остановлен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
