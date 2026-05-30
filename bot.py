import asyncio
import json
import random
import os
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, BigInteger, Float, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session

# ==================== КОНФИГ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "123456789").split(",")]

# ==================== БАЗА ДАННЫХ ====================
engine = create_engine("sqlite:///dark_mines.db", echo=False)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

# ==================== FSM ====================
class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_ban_reason = State()
    waiting_for_unban_id = State()
    waiting_for_give_coins = State()
    waiting_for_give_gems = State()
    waiting_for_set_vip = State()
    waiting_for_artifact_target = State()
    waiting_for_artifact_type = State()
    waiting_for_artifact_rarity = State()
    waiting_for_promo_code = State()
    waiting_for_promo_coins = State()
    waiting_for_promo_gems = State()
    waiting_for_promo_limit = State()
    waiting_for_promo_duration = State()
    waiting_for_promo_item = State()

class FightStates(StatesGroup):
    in_fight = State()

class GameStates(StatesGroup):
    waiting_for_promo_code = State()
    waiting_for_transfer = State()
    waiting_for_trust = State()

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
    title = Column(String, default="Начинающий шахтер")
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
    last_daily = Column(DateTime, nullable=True)
    daily_streak = Column(Integer, default=0)
    rebirth_count = Column(Integer, default=0)
    rebirth_multiplier = Column(Float, default=1.0)
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(String, default="")
    is_admin = Column(Boolean, default=False)
    notifications_enabled = Column(Boolean, default=True)
    inventory = relationship("Inventory", back_populates="user", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="owner", foreign_keys="Artifact.owner_id")
    
    @property
    def is_vip(self): return self.vip_level > 0
    @property
    def vip_title(self):
        return {0:"Новичок",1:"Бывалый шахтер",2:"Старатель",3:"Золотоискатель",4:"Хранитель недр",5:"Властелин шахт"}.get(self.vip_level,"Легенда")

class Artifact(Base):
    __tablename__ = "artifacts"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    artifact_type = Column(String, nullable=False)
    rarity = Column(String, default="common")
    level = Column(Integer, default=1)
    damage_bonus = Column(Integer, default=0)
    defense_bonus = Column(Integer, default=0)
    health_bonus = Column(Integer, default=0)
    crit_chance_bonus = Column(Float, default=0.0)
    crit_damage_bonus = Column(Float, default=0.0)
    dodge_bonus = Column(Float, default=0.0)
    lifesteal_bonus = Column(Float, default=0.0)
    exp_bonus = Column(Float, default=0.0)
    coin_bonus = Column(Float, default=0.0)
    equipped_slot = Column(Integer, default=0)
    trusted_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    trusted_until = Column(DateTime, nullable=True)
    owner = relationship("User", back_populates="artifacts", foreign_keys=[owner_id])
    
    @property
    def rarity_color(self):
        return {"common":"⬜","rare":"🟦","epic":"🟪","legendary":"🟨","mythical":"🟥"}.get(self.rarity,"⬜")
    @property
    def rarity_name(self):
        return {"common":"Обычный","rare":"Редкий","epic":"Эпический","legendary":"Легендарный","mythical":"Мифический"}.get(self.rarity,"Обычный")
    @property
    def type_name(self):
        return {"ring":"💍 Кольцо","amulet":"📿 Амулет","stone":"💎 Камень","scroll":"📜 Свиток","crystal":"🔮 Кристалл","rune":"ᚱ Руна"}.get(self.artifact_type,"Артефакт")

class Inventory(Base):
    __tablename__ = "inventory"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    item_type = Column(String)
    item_name = Column(String)
    quantity = Column(Integer, default=1)
    equipped = Column(Boolean, default=False)
    user = relationship("User", back_populates="inventory")

class Arena(Base):
    __tablename__ = "arenas"
    id = Column(Integer, primary_key=True)
    arena_number = Column(Integer, unique=True)
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

class PromoUsed(Base):
    __tablename__ = "promo_used"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    promo_id = Column(Integer, ForeignKey("promo_codes.id"))
    used_at = Column(DateTime, default=datetime.now)

# ==================== ДАННЫЕ ====================

ARTIFACTS = {
    "ring": [
        {"name":"Кольцо шахтера","rarity":"common","damage_bonus":5,"defense_bonus":3},
        {"name":"Кольцо удачи","rarity":"rare","crit_chance_bonus":0.05,"coin_bonus":0.1},
        {"name":"Кольцо вампира","rarity":"epic","lifesteal_bonus":0.1,"damage_bonus":15},
        {"name":"Кольцо невидимости","rarity":"legendary","dodge_bonus":0.15,"defense_bonus":20},
        {"name":"Кольцо всевластия","rarity":"mythical","damage_bonus":50,"defense_bonus":50,"health_bonus":500},
    ],
    "amulet": [
        {"name":"Амулет здоровья","rarity":"common","health_bonus":100},
        {"name":"Амулет силы","rarity":"rare","damage_bonus":20},
        {"name":"Амулет защиты","rarity":"rare","defense_bonus":25},
        {"name":"Амулет критов","rarity":"epic","crit_chance_bonus":0.12,"crit_damage_bonus":0.5},
        {"name":"Амулет дракона","rarity":"legendary","damage_bonus":35,"defense_bonus":35,"health_bonus":350},
    ],
    "stone": [
        {"name":"Камень удачи","rarity":"common","coin_bonus":0.15},
        {"name":"Камень опыта","rarity":"rare","exp_bonus":0.25},
        {"name":"Рубин крови","rarity":"epic","lifesteal_bonus":0.12,"damage_bonus":18},
        {"name":"Сапфир магии","rarity":"epic","defense_bonus":30},
        {"name":"Алмаз чистоты","rarity":"legendary","damage_bonus":40,"defense_bonus":30},
    ],
    "scroll": [
        {"name":"Свиток мудрости","rarity":"common","exp_bonus":0.2},
        {"name":"Свиток богатства","rarity":"rare","coin_bonus":0.25},
        {"name":"Свиток войны","rarity":"epic","damage_bonus":25,"crit_damage_bonus":0.4},
        {"name":"Свиток защиты","rarity":"rare","defense_bonus":20},
        {"name":"Свиток вампира","rarity":"epic","lifesteal_bonus":0.15,"health_bonus":150},
    ],
    "crystal": [
        {"name":"Кристалл маны","rarity":"common","health_bonus":80},
        {"name":"Кристалл силы","rarity":"rare","damage_bonus":15},
        {"name":"Кристалл защиты","rarity":"rare","defense_bonus":18},
        {"name":"Кристалл жизни","rarity":"epic","health_bonus":250,"lifesteal_bonus":0.08},
        {"name":"Кристалл удачи","rarity":"epic","crit_chance_bonus":0.1,"coin_bonus":0.2},
    ],
    "rune": [
        {"name":"Руна огня","rarity":"common","damage_bonus":8},
        {"name":"Руна льда","rarity":"common","defense_bonus":8},
        {"name":"Руна жизни","rarity":"rare","health_bonus":150},
        {"name":"Руна смерти","rarity":"epic","damage_bonus":20,"lifesteal_bonus":0.1},
        {"name":"Руна скорости","rarity":"rare","dodge_bonus":0.1},
    ],
}

ARENAS = [(1,"🏔 Заброшенная штольня","Старая выработка",100,50),(2,"🔥 Огненный карьер","Лавовые озера",150,75),(3,"❄ Мерзлая пещера","Ледяные гроты",200,100),(5,"⚡ Грозовой разлом","Ущелье молний",300,150),(10,"🏰 Каменоломня","Следы цивилизации",550,275),(15,"👁 Око бездны","Бездонная шахта",800,400),(20,"🌟 Астральный разлом","Редчайшие руды",1050,525),(25,"🔮 Хрустальный грот","Магические кристаллы",1300,650),(30,"⛓ Цепи Тартара","Врата в ад",1550,775),(40,"🏛 Храм забвения","Руины богов",2050,1025),(50,"👑 Тронный зал","Последняя шахта",3000,1500)]

BOSSES = {}
for an,_,_,_,_ in ARENAS:
    BOSSES[an] = [
        (f"Хранитель {an}","Страж",500+an*80,60+an*5,15+an//3,400+an*40,150+an*20,f"Руда {an}",0.4,None,0,0.05),
        (f"Старатель {an}","Проклятый",700+an*100,80+an*6,20+an//2,600+an*50,200+an*25,"Слиток",0.35,None,0,0.06),
        (f"Владыка {an}","Повелитель",1000+an*150,120+an*8,30+an*2,900+an*60,300+an*35,"Самородок",0.3,f"⭐ Ключ {an}",0.05,0.1),
    ]
BOSSES[1] = [("Крот-мутант","Вредитель",150,25,5,200,80,"Железная руда",0.5,None,0,0.05),("Каменный голем","Страж",250,35,8,300,100,"Медная руда",0.4,None,0,0.07),("Теневой шахтер","Проклятый",350,45,10,400,120,"Серебряная руда",0.6,"⭐ Кольцо",0.05,0.1)]

CASES = [
    {"name":"🎒 Снаряжение","desc":"Базовый набор","coins":1000,"gems":0,"vip":0,"items":[("500 золотых",0.5),("Каска шахтера",0.3),("Кирка новичка",0.2)]},
    {"name":"💎 Самоцветы","desc":"Сундук","coins":0,"gems":100,"vip":1,"items":[("1000 золотых",0.3),("50 самоцветов",0.3),("Сапфировая кирка",0.2),("Рубиновая броня",0.2)]},
    {"name":"👑 Старатель","desc":"Для опытных","coins":0,"gems":500,"vip":3,"items":[("5000 золотых",0.3),("200 самоцветов",0.2),("Алмазная кирка",0.2),("Золотая корона",0.15),("Яйцо дракона",0.15)]},
    {"name":"🌟 Легендарный","desc":"Для Властелинов","coins":0,"gems":1500,"vip":5,"items":[("10000 золотых",0.3),("500 самоцветов",0.2),("Кирка титанов",0.15),("Древний дракон",0.15),("Титул Король шахт",0.1),("Артефакт недр",0.1)]},
]

ARTIFACT_BAG = {"name":"🎒 Сумка","coins":5000,"gems":100,"vip":0,"count":1,"w":{"common":0.5,"rare":0.3,"epic":0.15,"legendary":0.04,"mythical":0.01}}
ARTIFACT_SUITCASE = {"name":"🧳 Чемодан","coins":0,"gems":500,"vip":2,"count":3,"w":{"common":0.2,"rare":0.35,"epic":0.25,"legendary":0.15,"mythical":0.05}}
ARTIFACT_ELITE = {"name":"👑 Элитный","coins":0,"gems":2000,"vip":5,"count":5,"w":{"common":0.05,"rare":0.15,"epic":0.25,"legendary":0.35,"mythical":0.2}}

# ==================== ФУНКЦИИ ====================

def init_db():
    Base.metadata.create_all(engine)
    s=SessionLocal()
    for a in ARENAS:
        if not s.query(Arena).filter(Arena.arena_number==a[0]).first():
            s.add(Arena(arena_number=a[0],name=a[1],description=a[2],reward_coins=a[3],reward_exp=a[4]))
    s.commit()
    for an,bs in BOSSES.items():
        ar=s.query(Arena).filter(Arena.arena_number==an).first()
        if ar:
            for i,bd in enumerate(bs,1):
                if not s.query(Boss).filter(Boss.arena_id==ar.id,Boss.boss_number==i).first():
                    s.add(Boss(arena_id=ar.id,boss_number=i,name=bd[0],title=bd[1],health=bd[2],damage=bd[3],defense=bd[4],reward_coins=bd[5],reward_exp=bd[6],drop_material=bd[7],drop_chance=bd[8],artifact_drop_chance=bd[11] if len(bd)>11 else 0.1))
    for c in CASES:
        if not s.query(Case).filter(Case.name==c["name"]).first():
            s.add(Case(name=c["name"],description=c["desc"],price_coins=c["coins"],price_gems=c["gems"],required_vip=c["vip"],drop_table=json.dumps(c["items"])))
    s.commit(); s.close()

def get_user(session, tg_id, create=True):
    u=session.query(User).filter(User.user_id==tg_id).first()
    if not u and create:
        u=User(user_id=tg_id)
        session.add(u); session.commit()
        for it in [("weapon","Кирка новичка",1,True),("armor","Роба шахтера",1,True),("material","Пайка шахтера",5,False)]:
            session.add(Inventory(user_id=u.id,item_type=it[0],item_name=it[1],quantity=it[2],equipped=it[3]))
        session.commit()
    return u

def update_stats(u):
    bd=10+(u.pickaxe_level-1)*4+(u.rebirth_count*8)
    bdf=5+(u.armor_level-1)*3+(u.helmet_level-1)*2+(u.boots_level-1)*1+(u.rebirth_count*4)
    bh=100+(u.armor_level-1)*15+(u.helmet_level-1)*10+(u.rebirth_count*25)
    cc,cd,dc,ls=0.1,2.0,0.05,0.0
    s=SessionLocal()
    for a in s.query(Artifact).filter(Artifact.owner_id==u.id,Artifact.equipped_slot>0).all():
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

def create_artifact(oid,weights=None):
    if not weights: weights={"common":0.5,"rare":0.3,"epic":0.13,"legendary":0.05,"mythical":0.02}
    r=random.choices(list(weights.keys()),weights=list(weights.values()))[0]
    t=random.choice(list(ARTIFACTS.keys()))
    av=[a for a in ARTIFACTS[t] if a["rarity"]==r] or ARTIFACTS[t]
    tp=random.choice(av)
    s=SessionLocal()
    art=Artifact(owner_id=oid,name=tp["name"],artifact_type=t,rarity=r,damage_bonus=tp.get("damage_bonus",0),defense_bonus=tp.get("defense_bonus",0),health_bonus=tp.get("health_bonus",0),crit_chance_bonus=tp.get("crit_chance_bonus",0.0),crit_damage_bonus=tp.get("crit_damage_bonus",0.0),dodge_bonus=tp.get("dodge_bonus",0.0),lifesteal_bonus=tp.get("lifesteal_bonus",0.0),exp_bonus=tp.get("exp_bonus",0.0),coin_bonus=tp.get("coin_bonus",0.0))
    s.add(art); s.commit(); s.refresh(art); s.close()
    return art

def open_pack(u,cfg):
    return [create_artifact(u.id,cfg["w"]) for _ in range(cfg["count"])]

def is_admin(uid): return uid in ADMIN_IDS

def main_menu():
    b=InlineKeyboardBuilder()
    for t,c in [("🏟 Шахты","m_arenas"),("👤 Профиль","m_profile"),("🎒 Инвентарь","m_inv"),("💍 Артефакты","m_arts"),("⚔️ Кузница","m_upgrade"),("📦 Кейсы","m_cases"),("🎒 Сумка артефактов","m_bag"),("🧳 Чемодан артефактов","m_case"),("👑 Элитный кейс","m_elite"),("🎁 Бонус","m_daily"),("🔄 Перерождение","m_rebirth"),("🏆 Топ","m_top"),("🎟 Промокод","m_promo"),("💎 Магазин","m_donate"),("❓ Помощь","m_help")]:
        b.button(text=t,callback_data=c)
    b.adjust(2)
    return b.as_markup()

def admin_kb():
    b=InlineKeyboardBuilder()
    for t,c in [("📢 Рассылка","a_broadcast"),("👤 Найти игрока","a_find"),("💰 Выдать золото","a_give_coins"),("💎 Выдать самоцветы","a_give_gems"),("👑 Выдать VIP","a_set_vip"),("🔨 Забанить","a_ban"),("🔓 Разбанить","a_unban"),("💍 Создать артефакт","a_artifact"),("🎟 Создать промокод","a_create_promo"),("📋 Список промокодов","a_list_promo"),("🗑 Удалить промокод","a_delete_promo"),("📊 Статистика","a_stats"),("◀ Назад","m_main")]:
        b.button(text=t,callback_data=c)
    b.adjust(1)
    return b.as_markup()

active_fights = {}

# ==================== ХЭНДЛЕРЫ ====================

@dp.message(Command("start"))
async def start(msg: Message):
    s=SessionLocal()
    u=get_user(s,msg.from_user.id)
    u.first_name=msg.from_user.first_name or ""; u.username=msg.from_user.username or ""
    s.commit(); s.close()
    await msg.answer("⛏ **ТЕМНЫЕ ШАХТЫ**\n/menu - меню\n/profile - профиль\n/admin - админка",reply_markup=main_menu())

@dp.message(Command("menu"))
async def menu(msg: Message): await msg.answer("⛏ Меню",reply_markup=main_menu())

@dp.message(Command("profile"))
async def profile(msg: Message):
    s=SessionLocal(); u=get_user(s,msg.from_user.id); update_stats(u); s.commit()
    await msg.answer(f"⛏ {u.first_name or u.username}\n🏅 {u.vip_title} ур.{u.vip_level}\n⚔️ Урон: {u.damage} | 🛡 Защита: {u.defense}\n❤️ HP: {u.health}/{u.max_health}\n💰 Золото: {u.coins} | 💎 Самоцветы: {u.gems}\n🏟 Шахта: {u.arena}/50"); s.close()

@dp.message(Command("admin"))
async def admin(msg: Message):
    if not is_admin(msg.from_user.id): await msg.answer("⛔"); return
    await msg.answer("⛏ Админ-панель\nВыберите действие:",reply_markup=admin_kb())

# ==================== ГЛАВНОЕ МЕНЮ ====================

@dp.callback_query(F.data=="m_main")
async def cb_main(cb: CallbackQuery): await cb.message.edit_text("⛏ Меню",reply_markup=main_menu()); await cb.answer()

@dp.callback_query(F.data=="m_profile")
async def cb_profile(cb: CallbackQuery):
    s=SessionLocal(); u=get_user(s,cb.from_user.id); update_stats(u); s.commit(); s.close()
    await cb.message.edit_text(f"⛏ {u.first_name}\n⚔️ {u.damage} | 💰 {u.coins}\n🏟 {u.arena}/50",reply_markup=main_menu()); await cb.answer()

@dp.callback_query(F.data=="m_inv")
async def cb_inv(cb: CallbackQuery):
    s=SessionLocal(); u=get_user(s,cb.from_user.id)
    inv=s.query(Inventory).filter(Inventory.user_id==u.id).all()
    txt="🎒 Инвентарь:\n"+"\n".join(f"{i.item_name} x{i.quantity}" for i in inv) if inv else "Пусто"
    s.close()
    await cb.message.edit_text(txt,reply_markup=main_menu()); await cb.answer()

@dp.callback_query(F.data=="m_arts")
async def cb_arts(cb: CallbackQuery):
    s=SessionLocal(); u=get_user(s,cb.from_user.id)
    arts=s.query(Artifact).filter(Artifact.owner_id==u.id).all()
    txt="💍 Артефакты:\n"+"\n".join(f"{a.rarity_color} {a.name} ур.{a.level} [{'✅' if a.equipped_slot else '❌'}]" for a in arts) if arts else "Нет артефактов"
    b=InlineKeyboardBuilder()
    for a in arts[:10]:
        b.button(text=f"{a.rarity_color} {a.name}",callback_data=f"art_{a.id}")
    b.button(text="◀ Назад",callback_data="m_main"); b.adjust(1)
    s.close()
    await cb.message.edit_text(txt,reply_markup=b.as_markup()); await cb.answer()

@dp.callback_query(F.data.startswith("art_"))
async def cb_art_info(cb: CallbackQuery):
    aid=int(cb.data.split("_")[1])
    s=SessionLocal(); a=s.query(Artifact).filter(Artifact.id==aid).first()
    if not a: await cb.answer("Не найден!"); s.close(); return
    txt=f"{a.rarity_color} {a.name} ({a.rarity_name})\n{a.type_name} ур.{a.level}\n⚔️ +{a.damage_bonus} | 🛡 +{a.defense_bonus} | ❤️ +{a.health_bonus}"
    b=InlineKeyboardBuilder()
    if a.equipped_slot: b.button(text="🔽 Снять",callback_data=f"uneq_{a.id}")
    else: b.button(text="⚡ Экипировать",callback_data=f"eq_{a.id}")
    b.button(text="🔄 Передать",callback_data=f"tr_{a.id}")
    b.button(text="🗑 Утилизировать",callback_data=f"disp_{a.id}")
    b.button(text="◀ Назад",callback_data="m_arts"); b.adjust(2)
    s.close()
    await cb.message.edit_text(txt,reply_markup=b.as_markup()); await cb.answer()

@dp.callback_query(F.data.startswith("eq_"))
async def cb_equip(cb: CallbackQuery):
    aid=int(cb.data.split("_")[1])
    s=SessionLocal(); u=get_user(s,cb.from_user.id)
    a=s.query(Artifact).filter(Artifact.id==aid,Artifact.owner_id==u.id).first()
    if not a: await cb.answer("Не найден!"); s.close(); return
    used=[x.equipped_slot for x in s.query(Artifact).filter(Artifact.owner_id==u.id,Artifact.equipped_slot>0).all()]
    free=[x for x in range(1,u.artifact_slots+1) if x not in used]
    if not free: await cb.answer("Нет свободных слотов!"); s.close(); return
    a.equipped_slot=free[0]; s.commit(); s.close()
    await cb.answer("Экипирован!"); await cb_arts(cb)

@dp.callback_query(F.data.startswith("uneq_"))
async def cb_unequip(cb: CallbackQuery):
    aid=int(cb.data.split("_")[1])
    s=SessionLocal(); u=get_user(s,cb.from_user.id)
    a=s.query(Artifact).filter(Artifact.id==aid,Artifact.owner_id==u.id).first()
    if a: a.equipped_slot=0; s.commit()
    s.close()
    await cb.answer("Снят!"); await cb_arts(cb)

@dp.callback_query(F.data.startswith("disp_"))
async def cb_dispose(cb: CallbackQuery):
    aid=int(cb.data.split("_")[1])
    s=SessionLocal(); u=get_user(s,cb.from_user.id)
    a=s.query(Artifact).filter(Artifact.id==aid,Artifact.owner_id==u.id).first()
    if a:
        rv={"common":1,"rare":5,"epic":20,"legendary":100,"mythical":500}.get(a.rarity,1)*a.level
        u.coins+=rv*100; u.gems+=rv; s.delete(a); s.commit()
        await cb.answer(f"+{rv*100}💰 +{rv}💎")
    s.close()
    await cb_arts(cb)

@dp.callback_query(F.data=="m_upgrade")
async def cb_upgrade(cb: CallbackQuery):
    s=SessionLocal(); u=get_user(s,cb.from_user.id)
    pc=1000*u.pickaxe_level; ac=800*u.armor_level
    txt=f"⚔️ Кузница\n💰 {u.coins} золота\n\n⛏ Кирка ур.{u.pickaxe_level} - {pc}💰\n🛡 Броня ур.{u.armor_level} - {ac}💰"
    b=InlineKeyboardBuilder()
    b.button(text="⛏ Кирка",callback_data="up_pick"); b.button(text="🛡 Броня",callback_data="up_armor")
    b.button(text="◀ Назад",callback_data="m_main"); b.adjust(2)
    s.close()
    await cb.message.edit_text(txt,reply_markup=b.as_markup()); await cb.answer()

@dp.callback_query(F.data=="up_pick")
async def cb_up_pick(cb: CallbackQuery):
    s=SessionLocal(); u=get_user(s,cb.from_user.id)
    c=1000*u.pickaxe_level
    if u.coins<c: await cb.answer(f"Нужно {c}💰!"); s.close(); return
    u.coins-=c; u.pickaxe_level+=1; update_stats(u); s.commit(); s.close()
    await cb.answer("Улучшено!"); await cb_upgrade(cb)

@dp.callback_query(F.data=="up_armor")
async def cb_up_armor(cb: CallbackQuery):
    s=SessionLocal(); u=get_user(s,cb.from_user.id)
    c=800*u.armor_level
    if u.coins<c: await cb.answer(f"Нужно {c}💰!"); s.close(); return
    u.coins-=c; u.armor_level+=1; update_stats(u); s.commit(); s.close()
    await cb.answer("Улучшено!"); await cb_upgrade(cb)

@dp.callback_query(F.data=="m_cases")
async def cb_cases(cb: CallbackQuery):
    s=SessionLocal(); u=get_user(s,cb.from_user.id); cases=s.query(Case).all()
    txt="📦 Кейсы:\n\n"
    b=InlineKeyboardBuilder()
    for c in cases:
        if u.vip_level>=c.required_vip:
            pr=f"💰{c.price_coins}" if c.price_coins else f"💎{c.price_gems}"
            txt+=f"{c.name} - {pr}\n"
            b.button(text=f"{c.name} {pr}",callback_data=f"case_{c.id}")
    b.button(text="◀ Назад",callback_data="m_main"); b.adjust(1)
    s.close()
    await cb.message.edit_text(txt,reply_markup=b.as_markup()); await cb.answer()

@dp.callback_query(F.data.startswith("case_"))
async def cb_open_case(cb: CallbackQuery):
    cid=int(cb.data.split("_")[1])
    s=SessionLocal(); u=get_user(s,cb.from_user.id); c=s.query(Case).filter(Case.id==cid).first()
    if not c: await cb.answer("Не найден!"); s.close(); return
    if c.price_coins>0 and u.coins<c.price_coins: await cb.answer("Мало💰!"); s.close(); return
    if c.price_gems>0 and u.gems<c.price_gems: await cb.answer("Мало💎!"); s.close(); return
    u.coins-=c.price_coins; u.gems-=c.price_gems
    items=json.loads(c.drop_table)
    r=random.random()
    cum=0; reward=items[0][0]
    for name,chance in items:
        cum+=chance
        if r<=cum: reward=name; break
    if "золотых" in reward: u.coins+=int(reward.split()[0])
    elif "самоцветов" in reward: u.gems+=int(reward.split()[0])
    else: s.add(Inventory(user_id=u.id,item_type="special",item_name=reward,quantity=1))
    s.commit(); s.close()
    await cb.message.edit_text(f"🎉 {reward}!",reply_markup=main_menu()); await cb.answer()

@dp.callback_query(F.data=="m_bag")
async def cb_bag(cb: CallbackQuery):
    s=SessionLocal(); u=get_user(s,cb.from_user.id)
    if u.coins<ARTIFACT_BAG["coins"]: await cb.answer("Мало💰!"); s.close(); return
    u.coins-=ARTIFACT_BAG["coins"]
    arts=open_pack(u,ARTIFACT_BAG); s.commit(); s.close()
    await cb.message.edit_text("🎒 "+"\n".join(f"{a.rarity_color} {a.name}" for a in arts),reply_markup=main_menu()); await cb.answer()

@dp.callback_query(F.data=="m_case")
async def cb_case(cb: CallbackQuery):
    s=SessionLocal(); u=get_user(s,cb.from_user.id)
    if u.vip_level<ARTIFACT_SUITCASE["vip"]: await cb.answer("VIP 2+!"); s.close(); return
    if u.gems<ARTIFACT_SUITCASE["gems"]: await cb.answer("Мало💎!"); s.close(); return
    u.gems-=ARTIFACT_SUITCASE["gems"]
    arts=open_pack(u,ARTIFACT_SUITCASE); s.commit(); s.close()
    await cb.message.edit_text("🧳 "+"\n".join(f"{a.rarity_color} {a.name}" for a in arts),reply_markup=main_menu()); await cb.answer()

@dp.callback_query(F.data=="m_elite")
async def cb_elite(cb: CallbackQuery):
    s=SessionLocal(); u=get_user(s,cb.from_user.id)
    if u.vip_level<ARTIFACT_ELITE["vip"]: await cb.answer("VIP 5!"); s.close(); return
    if u.gems<ARTIFACT_ELITE["gems"]: await cb.answer("Мало💎!"); s.close(); return
    u.gems-=ARTIFACT_ELITE["gems"]
    arts=open_pack(u,ARTIFACT_ELITE); s.commit(); s.close()
    await cb.message.edit_text("👑 "+"\n".join(f"{a.rarity_color} {a.name}" for a in arts),reply_markup=main_menu()); await cb.answer()

@dp.callback_query(F.data=="m_daily")
async def cb_daily(cb: CallbackQuery):
    s=SessionLocal(); u=get_user(s,cb.from_user.id)
    now=datetime.now()
    if u.last_daily and u.last_daily.date()==now.date(): await cb.answer("Уже получен!"); s.close(); return
    if u.last_daily and (now-u.last_daily).days>1: u.daily_streak=0
    u.daily_streak+=1; u.last_daily=now
    bonus=min(u.daily_streak,7); coins=500*bonus; gems=25*bonus
    if u.is_vip: coins=int(coins*1.5); gems=int(gems*1.5)
    u.coins+=coins; u.gems+=gems; s.commit(); s.close()
    await cb.message.edit_text(f"🎁 +{coins}💰 +{gems}💎\nСерия: {u.daily_streak}/7",reply_markup=main_menu()); await cb.answer()

@dp.callback_query(F.data=="m_rebirth")
async def cb_rebirth(cb: CallbackQuery):
    s=SessionLocal(); u=get_user(s,cb.from_user.id)
    if u.arena<50: await cb.answer("Нужна 50 шахта!"); s.close(); return
    u.arena=1; u.pickaxe_level=1; u.armor_level=1; u.coins=5000; u.gems=500
    u.rebirth_count+=1; u.rebirth_multiplier+=0.5
    s.query(Inventory).filter(Inventory.user_id==u.id).delete()
    s.add(Inventory(user_id=u.id,item_type="weapon",item_name="Кирка новичка",equipped=True))
    s.add(Inventory(user_id=u.id,item_type="armor",item_name="Роба шахтера",equipped=True))
    s.commit(); s.close()
    await cb.message.edit_text(f"🔄 Перерождение {u.rebirth_count}!\nx{u.rebirth_multiplier} множитель",reply_markup=main_menu()); await cb.answer()

@dp.callback_query(F.data=="m_top")
async def cb_top(cb: CallbackQuery):
    s=SessionLocal()
    top=s.query(User).order_by(User.coins.desc()).limit(10).all()
    txt="🏆 Топ:\n"+"\n".join(f"{i+1}. {u.first_name or u.username} - {u.coins}💰" for i,u in enumerate(top))
    s.close()
    await cb.message.edit_text(txt,reply_markup=main_menu()); await cb.answer()

@dp.callback_query(F.data=="m_promo")
async def cb_promo(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🎟 Введите промокод:"); await state.set_state(GameStates.waiting_for_promo_code); await cb.answer()

@dp.message(GameStates.waiting_for_promo_code)
async def promo_use(msg: Message, state: FSMContext):
    s=SessionLocal()
    p=s.query(PromoCode).filter(PromoCode.code==msg.text.upper(),PromoCode.is_active==True).first()
    if not p: await msg.answer("❌"); await state.clear(); s.close(); return
    if not p.is_permanent and p.expires_at and p.expires_at<datetime.now(): await msg.answer("❌ Истек!"); await state.clear(); s.close(); return
    if p.uses_count>=p.uses_limit: await msg.answer("❌ Лимит!"); await state.clear(); s.close(); return
    u=get_user(s,msg.from_user.id)
    if s.query(PromoUsed).filter(PromoUsed.user_id==u.id,PromoUsed.promo_id==p.id).first(): await msg.answer("❌ Уже использован!"); await state.clear(); s.close(); return
    u.coins+=p.reward_coins; u.gems+=p.reward_gems
    if p.reward_item: s.add(Inventory(user_id=u.id,item_type="special",item_name=p.reward_item,quantity=1))
    s.add(PromoUsed(user_id=u.id,promo_id=p.id)); p.uses_count+=1; s.commit(); s.close()
    await msg.answer("✅ Активирован!",reply_markup=main_menu()); await state.clear()

@dp.callback_query(F.data=="m_donate")
async def cb_donate(cb: CallbackQuery):
    await cb.message.edit_text("💎 Магазин\n👑 Статусы навсегда:\n⭐ Бывалый - 99₽\n🔥 Старатель - 299₽\n💎 Золотоискатель - 699₽\n✨ Хранитель - 1499₽\n👑 Властелин - 3499₽\n\n💎 Самоцветы от 49₽\n📝 @DEDACHAAVIVA",reply_markup=main_menu()); await cb.answer()

@dp.callback_query(F.data=="m_help")
async def cb_help(cb: CallbackQuery):
    await cb.message.edit_text("⛏ Помощь\n/menu /profile /admin\n🎒 Сумка - 5000💰\n🧳 Чемодан - 500💎\n👑 Элитный - 2000💎\n📦 Кейсы за 💰 и 💎\n🎁 Ежедневный бонус\n🔄 Перерождение на 50 шахте",reply_markup=main_menu()); await cb.answer()

# ==================== АДМИНКА ====================

@dp.callback_query(F.data=="admin_panel")
async def cb_admin_panel(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): await cb.answer("⛔"); return
    await cb.message.edit_text("⛏ Админ-панель",reply_markup=admin_kb()); await cb.answer()

@dp.callback_query(F.data=="a_broadcast")
async def cb_abroadcast(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📢 Введите текст рассылки:"); await state.set_state(AdminStates.waiting_for_broadcast); await cb.answer()

@dp.message(AdminStates.waiting_for_broadcast)
async def broadcast(msg: Message, state: FSMContext):
    s=SessionLocal(); users=s.query(User).filter(User.notifications_enabled==True).all()
    ok=0
    for u in users:
        try: await bot.send_message(u.user_id,f"📢 {msg.text}"); ok+=1
        except: pass
    s.close(); await state.clear()
    await msg.answer(f"✅ Отправлено {ok} пользователям",reply_markup=admin_kb())

@dp.callback_query(F.data=="a_find")
async def cb_afind(cb: CallbackQuery):
    s=SessionLocal()
    users=s.query(User).order_by(User.user_id.desc()).limit(20).all()
    txt="👥 Последние игроки:\n\n"
    for u in users:
        txt+=f"ID: `{u.user_id}` - {u.first_name or 'Нет'}\n💰{u.coins} 💎{u.gems} 🏟{u.arena}\n\n"
    s.close()
    await cb.message.edit_text(txt,reply_markup=admin_kb()); await cb.answer()

@dp.callback_query(F.data=="a_give_coins")
async def cb_acoins(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("💰 Введите ID и сумму: `123456789 10000`"); await state.set_state(AdminStates.waiting_for_give_coins); await cb.answer()

@dp.message(AdminStates.waiting_for_give_coins)
async def give_coins(msg: Message, state: FSMContext):
    try:
        tid,amount=msg.text.split(); tid=int(tid); amount=int(amount)
        s=SessionLocal(); u=get_user(s,tid); u.coins+=amount; s.commit(); s.close()
        await msg.answer(f"✅ +{amount}💰 игроку {tid}",reply_markup=admin_kb())
    except: await msg.answer("❌ Формат: ID сумма")
    await state.clear()

@dp.callback_query(F.data=="a_give_gems")
async def cb_agems(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("💎 Введите ID и сумму: `123456789 500`"); await state.set_state(AdminStates.waiting_for_give_gems); await cb.answer()

@dp.message(AdminStates.waiting_for_give_gems)
async def give_gems(msg: Message, state: FSMContext):
    try:
        tid,amount=msg.text.split(); tid=int(tid); amount=int(amount)
        s=SessionLocal(); u=get_user(s,tid); u.gems+=amount; s.commit(); s.close()
        await msg.answer(f"✅ +{amount}💎 игроку {tid}",reply_markup=admin_kb())
    except: await msg.answer("❌ Формат: ID сумма")
    await state.clear()

@dp.callback_query(F.data=="a_set_vip")
async def cb_avip(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("👑 Введите ID и уровень (1-5): `123456789 3`"); await state.set_state(AdminStates.waiting_for_set_vip); await cb.answer()

@dp.message(AdminStates.waiting_for_set_vip)
async def set_vip(msg: Message, state: FSMContext):
    try:
        tid,level=msg.text.split(); tid=int(tid); level=int(level)
        if level<0 or level>5: await msg.answer("❌ 1-5!"); return
        s=SessionLocal(); u=get_user(s,tid); u.vip_level=level; s.commit(); s.close()
        await msg.answer(f"✅ VIP {level} игроку {tid}",reply_markup=admin_kb())
    except: await msg.answer("❌ Формат: ID уровень")
    await state.clear()

@dp.callback_query(F.data=="a_ban")
async def cb_aban(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🔨 Введите ID и причину: `123456789 спам`"); await state.set_state(AdminStates.waiting_for_ban_reason); await cb.answer()

@dp.message(AdminStates.waiting_for_ban_reason)
async def ban_user(msg: Message, state: FSMContext):
    try:
        parts=msg.text.split(maxsplit=1); tid=int(parts[0]); reason=parts[1] if len(parts)>1 else "Нарушение"
        s=SessionLocal(); u=get_user(s,tid); u.is_banned=True; u.ban_reason=reason; s.commit(); s.close()
        await msg.answer(f"✅ Игрок {tid} забанен\n{reason}",reply_markup=admin_kb())
    except: await msg.answer("❌ Ошибка")
    await state.clear()

@dp.callback_query(F.data=="a_unban")
async def cb_aunban(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🔓 Введите ID для разбана:"); await state.set_state(AdminStates.waiting_for_unban_id); await cb.answer()

@dp.message(AdminStates.waiting_for_unban_id)
async def unban_user(msg: Message, state: FSMContext):
    try:
        tid=int(msg.text)
        s=SessionLocal(); u=get_user(s,tid); u.is_banned=False; u.ban_reason=""; s.commit(); s.close()
        await msg.answer(f"✅ Игрок {tid} разбанен",reply_markup=admin_kb())
    except: await msg.answer("❌ Ошибка")
    await state.clear()

@dp.callback_query(F.data=="a_stats")
async def cb_astats(cb: CallbackQuery):
    s=SessionLocal()
    txt=f"📊 Статистика:\n👥 Игроков: {s.query(User).count()}\n🔨 Забанено: {s.query(User).filter(User.is_banned==True).count()}\n👑 VIP: {s.query(User).filter(User.vip_level>0).count()}\n💍 Артефактов: {s.query(Artifact).count()}\n🎟 Промокодов: {s.query(PromoCode).count()}"
    s.close()
    await cb.message.edit_text(txt,reply_markup=admin_kb()); await cb.answer()

@dp.callback_query(F.data=="a_list_promo")
async def cb_list_promo(cb: CallbackQuery):
    s=SessionLocal()
    promos=s.query(PromoCode).order_by(PromoCode.created_at.desc()).limit(20).all()
    txt="📋 Промокоды:\n\n" if promos else "Нет промокодов"
    for p in promos:
        pt="♾️" if p.is_permanent else "📅"; st="✅" if p.is_active else "❌"
        txt+=f"{pt}{st} `{p.code}` - {p.uses_count}/{p.uses_limit}\n"
    s.close()
    await cb.message.edit_text(txt,reply_markup=admin_kb()); await cb.answer()

@dp.callback_query(F.data=="a_delete_promo")
async def cb_delete_promo_menu(cb: CallbackQuery):
    s=SessionLocal(); promos=s.query(PromoCode).all()
    if not promos: await cb.answer("Нет промокодов!"); s.close(); return
    b=InlineKeyboardBuilder()
    for p in promos[:20]: b.button(text=f"🗑 {p.code}",callback_data=f"delpromo_{p.id}")
    b.button(text="◀ Назад",callback_data="admin_panel"); b.adjust(2)
    s.close()
    await cb.message.edit_text("Выберите для удаления:",reply_markup=b.as_markup()); await cb.answer()

@dp.callback_query(F.data.startswith("delpromo_"))
async def cb_delete_promo_confirm(cb: CallbackQuery):
    pid=int(cb.data.split("_")[1])
    s=SessionLocal(); p=s.query(PromoCode).filter(PromoCode.id==pid).first()
    if p: code=p.code; s.delete(p); s.commit(); await cb.answer(f"Удалён {code}!")
    s.close()
    await cb.message.edit_text("✅ Промокод удалён!",reply_markup=admin_kb()); await cb.answer()

@dp.callback_query(F.data=="a_artifact")
async def cb_aartifact(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("💍 Введите ID игрока:"); await state.set_state(AdminStates.waiting_for_artifact_target); await cb.answer()

@dp.message(AdminStates.waiting_for_artifact_target)
async def a_target(msg: Message, state: FSMContext):
    await state.update_data(tid=int(msg.text))
    b=InlineKeyboardBuilder()
    for t in ["ring","amulet","stone","scroll","crystal","rune"]: b.button(text=t,callback_data=f"atype_{t}")
    b.adjust(2)
    await msg.answer("Тип:",reply_markup=b.as_markup()); await state.set_state(AdminStates.waiting_for_artifact_type)

@dp.callback_query(F.data.startswith("atype_"),AdminStates.waiting_for_artifact_type)
async def a_type(cb: CallbackQuery, state: FSMContext):
    await state.update_data(atype=cb.data.split("_")[1])
    b=InlineKeyboardBuilder()
    for r in ["common","rare","epic","legendary","mythical"]: b.button(text=r,callback_data=f"ararity_{r}")
    b.adjust(2)
    await cb.message.edit_text("Редкость:",reply_markup=b.as_markup()); await state.set_state(AdminStates.waiting_for_artifact_rarity); await cb.answer()

@dp.callback_query(F.data.startswith("ararity_"),AdminStates.waiting_for_artifact_rarity)
async def a_rarity(cb: CallbackQuery, state: FSMContext):
    data=await state.get_data(); tid=data["tid"]; at=data["atype"]; r=cb.data.split("_")[1]
    s=SessionLocal(); target=get_user(s,tid)
    av=[a for a in ARTIFACTS[at] if a["rarity"]==r] or ARTIFACTS[at]
    tp=random.choice(av)
    art=Artifact(owner_id=target.id,name=tp["name"],artifact_type=at,rarity=r,damage_bonus=tp.get("damage_bonus",0),defense_bonus=tp.get("defense_bonus",0),health_bonus=tp.get("health_bonus",0))
    s.add(art); s.commit(); s.close()
    await cb.message.edit_text(f"✅ Артефакт {art.name} выдан!",reply_markup=admin_kb())
    try: await bot.send_message(tid,f"🎁 Админ выдал: {art.name}!")
    except: pass
    await state.clear(); await cb.answer()

@dp.callback_query(F.data=="a_create_promo")
async def cb_create_promo_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🎟 Введите КОД промокода:"); await state.set_state(AdminStates.waiting_for_promo_code); await cb.answer()

@dp.message(AdminStates.waiting_for_promo_code)
async def promo_code_input(msg: Message, state: FSMContext):
    code=msg.text.upper()
    s=SessionLocal()
    if s.query(PromoCode).filter(PromoCode.code==code).first(): await msg.answer("❌ Уже существует!"); s.close(); return
    s.close()
    await state.update_data(promo_code=code); await msg.answer("💰 Введите монеты:"); await state.set_state(AdminStates.waiting_for_promo_coins)

@dp.message(AdminStates.waiting_for_promo_coins)
async def promo_coins_input(msg: Message, state: FSMContext):
    await state.update_data(promo_coins=int(msg.text)); await msg.answer("💎 Введите самоцветы:"); await state.set_state(AdminStates.waiting_for_promo_gems)

@dp.message(AdminStates.waiting_for_promo_gems)
async def promo_gems_input(msg: Message, state: FSMContext):
    await state.update_data(promo_gems=int(msg.text)); await msg.answer("👥 Лимит использований:"); await state.set_state(AdminStates.waiting_for_promo_limit)

@dp.message(AdminStates.waiting_for_promo_limit)
async def promo_limit_input(msg: Message, state: FSMContext):
    await state.update_data(promo_limit=int(msg.text)); await msg.answer("⏰ Дней или 'permanent':"); await state.set_state(AdminStates.waiting_for_promo_duration)

@dp.message(AdminStates.waiting_for_promo_duration)
async def promo_duration_input(msg: Message, state: FSMContext):
    dur=msg.text.lower(); is_perm=dur=="permanent"; days=int(dur) if not is_perm else 0
    await state.update_data(promo_permanent=is_perm,promo_days=days); await msg.answer("🎁 Предмет или '-' если без:"); await state.set_state(AdminStates.waiting_for_promo_item)

@dp.message(AdminStates.waiting_for_promo_item)
async def promo_item_input(msg: Message, state: FSMContext):
    item=msg.text if msg.text!="-" else None
    data=await state.get_data()
    s=SessionLocal()
    exp=None if data["promo_permanent"] else datetime.now()+timedelta(days=data["promo_days"])
    s.add(PromoCode(code=data["promo_code"],reward_coins=data["promo_coins"],reward_gems=data["promo_gems"],uses_limit=data["promo_limit"],expires_at=exp,is_permanent=data["promo_permanent"],reward_item=item))
    s.commit(); s.close()
    await msg.answer(f"✅ Промокод {data['promo_code']} создан!",reply_markup=admin_kb()); await state.clear()

# ==================== ШАХТЫ И БОИ ====================

@dp.callback_query(F.data=="m_arenas")
async def cb_arenas(cb: CallbackQuery):
    s=SessionLocal(); u=get_user(s,cb.from_user.id)
    b=InlineKeyboardBuilder()
    for an,nm,_,_,_ in ARENAS:
        b.button(text=f"{'✅' if an<=u.arena else '🔒'} {an}",callback_data=f"ar_{an}")
    b.button(text="◀",callback_data="m_main"); b.adjust(5)
    s.close()
    await cb.message.edit_text(f"⛏ Шахты (текущая: {u.arena}/50)",reply_markup=b.as_markup()); await cb.answer()

@dp.callback_query(F.data.startswith("ar_"))
async def cb_arena(cb: CallbackQuery):
    an=int(cb.data.split("_")[1])
    s=SessionLocal(); u=get_user(s,cb.from_user.id)
    if an>u.arena: await cb.answer("Закрыта!"); s.close(); return
    ar=s.query(Arena).filter(Arena.arena_number==an).first()
    bs=s.query(Boss).filter(Boss.arena_id==ar.id).all()
    b=InlineKeyboardBuilder()
    for boss in bs: b.button(text=f"⚔️ {boss.name}",callback_data=f"bs_{an}_{boss.boss_number}")
    b.button(text="◀",callback_data="m_arenas"); b.adjust(1)
    s.close()
    await cb.message.edit_text(f"⛏ {ar.name}\n{ar.description}\n💰 {ar.reward_coins}",reply_markup=b.as_markup()); await cb.answer()

@dp.callback_query(F.data.startswith("bs_"))
async def cb_boss(cb: CallbackQuery):
    _,an,bn=cb.data.split("_"); an=int(an); bn=int(bn)
    s=SessionLocal(); u=get_user(s,cb.from_user.id); update_stats(u)
    ar=s.query(Arena).filter(Arena.arena_number==an).first()
    boss=s.query(Boss).filter(Boss.arena_id==ar.id,Boss.boss_number==bn).first()
    b=InlineKeyboardBuilder()
    b.button(text="⚔️ В БОЙ!",callback_data=f"fg_{an}_{bn}")
    b.button(text="◀",callback_data=f"ar_{an}")
    s.close()
    await cb.message.edit_text(f"👹 {boss.name}\n❤️ {boss.health} | ⚔️ {boss.damage}\n💰 {boss.reward_coins}\n\nТы: ⚔️ {u.damage}",reply_markup=b.as_markup()); await cb.answer()

@dp.callback_query(F.data.startswith("fg_"))
async def cb_fight(cb: CallbackQuery, state: FSMContext):
    _,an,bn=cb.data.split("_"); an=int(an); bn=int(bn)
    s=SessionLocal(); u=get_user(s,cb.from_user.id); update_stats(u)
    ar=s.query(Arena).filter(Arena.arena_number==an).first()
    boss=s.query(Boss).filter(Boss.arena_id==ar.id,Boss.boss_number==bn).first()
    active_fights[cb.from_user.id]={"an":an,"bn":bn,"uhp":u.max_health,"bhp":boss.health}
    await state.set_state(FightStates.in_fight); s.close()
    b=InlineKeyboardBuilder()
    b.button(text="⚔️ Атаковать",callback_data=f"atk_{an}_{bn}")
    b.button(text="💊 Зелье",callback_data=f"pot_{an}_{bn}")
    b.button(text="🏃 Сбежать",callback_data="m_arenas"); b.adjust(2)
    await cb.message.edit_text(f"⚔️ БОЙ!\n👹 {boss.name}\n❤️ {boss.health}\n\nТы: ❤️ {u.max_health} | ⚔️ {u.damage}",reply_markup=b.as_markup()); await cb.answer()

@dp.callback_query(F.data.startswith("pot_"),FightStates.in_fight)
async def cb_potion(cb: CallbackQuery):
    if cb.from_user.id not in active_fights: await cb.answer("Нет боя!"); return
    f=active_fights[cb.from_user.id]
    s=SessionLocal(); u=get_user(s,cb.from_user.id)
    pot=s.query(Inventory).filter(Inventory.user_id==u.id,Inventory.item_name=="Шахтерское зелье").first()
    if not pot or pot.quantity<1: await cb.answer("Нет зелий!"); s.close(); return
    pot.quantity-=1
    if pot.quantity<=0: s.delete(pot)
    heal=50; f["uhp"]=min(f["uhp"]+heal,u.max_health); s.commit(); s.close()
    await cb.answer(f"+{heal} HP!")

@dp.callback_query(F.data.startswith("atk_"),FightStates.in_fight)
async def cb_attack(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in active_fights: await cb.answer("Нет боя!"); await state.clear(); return
    f=active_fights[cb.from_user.id]; _,an,bn=cb.data.split("_"); an=int(an); bn=int(bn)
    s=SessionLocal(); u=get_user(s,cb.from_user.id); update_stats(u)
    ar=s.query(Arena).filter(Arena.arena_number==an).first()
    boss=s.query(Boss).filter(Boss.arena_id==ar.id,Boss.boss_number==bn).first()
    dmg=max(1,u.damage-boss.defense//2)
    if random.random()<u.critical_chance: dmg=int(dmg*u.critical_damage)
    f["bhp"]-=dmg
    if f["bhp"]<=0:
        u.coins+=boss.reward_coins; u.exp+=boss.reward_exp; u.gems+=boss.reward_gems
        txt=f"🏆 Победа!\n💰 +{boss.reward_coins}"
        if random.random()<boss.artifact_drop_chance:
            art=create_artifact(u.id); txt+=f"\n💍 +{art.rarity_color} {art.name}!"
        if an==u.arena and an<50: u.arena+=1; txt+=f"\n⛏ Шахта {u.arena} открыта!"
        s.commit(); s.close(); del active_fights[cb.from_user.id]; await state.clear()
        await cb.message.edit_text(txt,reply_markup=main_menu()); await cb.answer("Победа!"); return
    bdmg=max(1,boss.damage-u.defense//2)
    f["uhp"]-=bdmg
    if f["uhp"]<=0:
        s.close(); del active_fights[cb.from_user.id]; await state.clear()
        await cb.message.edit_text("💀 Поражение!",reply_markup=main_menu()); await cb.answer("Поражение!"); return
    s.close()
    b=InlineKeyboardBuilder()
    b.button(text="⚔️ Атаковать",callback_data=f"atk_{an}_{bn}")
    b.button(text="💊 Зелье",callback_data=f"pot_{an}_{bn}")
    b.button(text="🏃 Сбежать",callback_data="m_arenas"); b.adjust(2)
    await cb.message.edit_text(f"⚔️ Ты нанёс {dmg}\n👹 HP: {f['bhp']}/{boss.health}\n❤️ Ты: {f['uhp']}/{u.max_health}",reply_markup=b.as_markup()); await cb.answer()

# ==================== ЗАПУСК ====================

async def main():
    global bot
    init_db()
    session = AiohttpSession(timeout=60)
    bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode="HTML"))
    print("⛏ Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
