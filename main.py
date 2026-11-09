import asyncio
import logging
import os
import sys
import urllib.parse
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from config import BOT_TOKEN, ADMIN_IDS
from database import (
    init_db,
    save_application,
    update_application_status,
    get_application_by_id,
    get_applications_count,
    get_recent_applications,
    add_admin,
    get_admins,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# FSM States
class PilotApplication(StatesGroup):
    waiting_for_role = State()
    waiting_for_name = State()
    waiting_for_institution = State()
    waiting_for_faculty = State()
    waiting_for_group = State()
    waiting_for_count = State()
    waiting_for_chat_platform = State()
    waiting_for_schedule_source = State()
    waiting_for_cancel_freq = State()
    waiting_for_cancel_channel = State()
    waiting_for_curator_report = State()
    waiting_for_readiness = State()
    waiting_for_contact = State()
    waiting_for_confirmation = State()

# Inline Keyboards
def get_role_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Староста группы", callback_data="role_starosta"),
            InlineKeyboardButton(text="Заместитель старосты", callback_data="role_deputy")
        ],
        [
            InlineKeyboardButton(text="Куратор / Преподаватель", callback_data="role_curator"),
            InlineKeyboardButton(text="Студент-активист", callback_data="role_student")
        ],
        [
            InlineKeyboardButton(text="Отмена", callback_data="action_cancel")
        ]
    ])

def get_chat_platform_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Telegram", callback_data="chat_tg"),
            InlineKeyboardButton(text="ВКонтакте", callback_data="chat_vk")
        ],
        [
            InlineKeyboardButton(text="Сферум / MAX", callback_data="chat_sferum"),
            InlineKeyboardButton(text="Другое (создадим в TG)", callback_data="chat_other")
        ],
        [
            InlineKeyboardButton(text="Отмена", callback_data="action_cancel")
        ]
    ])

def get_schedule_source_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Сайт / портал вуза", callback_data="sch_site"),
            InlineKeyboardButton(text="Excel / PDF файл", callback_data="sch_excel")
        ],
        [
            InlineKeyboardButton(text="Фото со стенда", callback_data="sch_photo"),
            InlineKeyboardButton(text="Куратор шлет в чат", callback_data="sch_curator")
        ],
        [
            InlineKeyboardButton(text="Отмена", callback_data="action_cancel")
        ]
    ])

def get_cancel_freq_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Каждую неделю (1–3 раза)", callback_data="freq_weekly"),
            InlineKeyboardButton(text="1–2 раза в месяц", callback_data="freq_monthly")
        ],
        [
            InlineKeyboardButton(text="Редко / почти не бывает", callback_data="freq_rare")
        ],
        [
            InlineKeyboardButton(text="Отмена", callback_data="action_cancel")
        ]
    ])

def get_cancel_channel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Пишут старосте в ЛС", callback_data="chan_pm"),
            InlineKeyboardButton(text="Публикуют в СДО / на сайте", callback_data="chan_sdo")
        ],
        [
            InlineKeyboardButton(text="Сообщают через куратора", callback_data="chan_curator"),
            InlineKeyboardButton(text="Узнаем у двери аудитории", callback_data="chan_door")
        ],
        [
            InlineKeyboardButton(text="Отмена", callback_data="action_cancel")
        ]
    ])

def get_curator_report_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да, каждую неделю / месяц", callback_data="rep_regular"),
            InlineKeyboardButton(text="Только в конце семестра", callback_data="rep_session")
        ],
        [
            InlineKeyboardButton(text="Нет, отмечаем для себя", callback_data="rep_self")
        ],
        [
            InlineKeyboardButton(text="Отмена", callback_data="action_cancel")
        ]
    ])

def get_readiness_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да, готовы к тесту с 20.11", callback_data="ready_yes")
        ],
        [
            InlineKeyboardButton(text="Готовы, если поможете настроить", callback_data="ready_help")
        ],
        [
            InlineKeyboardButton(text="Хотим сначала задать вопросы", callback_data="ready_questions")
        ],
        [
            InlineKeyboardButton(text="Отмена", callback_data="action_cancel")
        ]
    ])

def get_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Подтвердить и отправить заявку", callback_data="confirm_send")
        ],
        [
            InlineKeyboardButton(text="Заполнить заново", callback_data="confirm_restart"),
            InlineKeyboardButton(text="Отменить", callback_data="action_cancel")
        ]
    ])

def build_contact_url(template: str = "Здравствуйте! Пишу по поводу проекта «РИТМ».") -> str:
    return "https://t.me/spizhy?text=" + urllib.parse.quote(template)

def get_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Подать заявку на пилот", callback_data="action_start_apply")
        ],
        [
            InlineKeyboardButton(text="📖 О проекте «Ритм»", callback_data="action_about"),
            InlineKeyboardButton(
                text="💬 Написать координатору",
                url=build_contact_url("Здравствуйте! Пишу по поводу проекта «РИТМ».")
            )
        ]
    ])

def get_contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Поделиться контактом", request_contact=True)],
            [KeyboardButton(text="Введу контакт вручную")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_admin_action_keyboard(app_id: int, username: str = "", user_id: int = 0) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="Одобрить заявку", callback_data=f"admin_approve_{app_id}"),
            InlineKeyboardButton(text="Отклонить", callback_data=f"admin_reject_{app_id}")
        ]
    ]
    if username:
        buttons.append([InlineKeyboardButton(text="Написать в Telegram", url=f"https://t.me/{username}")])
    elif user_id:
        buttons.append([InlineKeyboardButton(text="Профиль заявителя", url=f"tg://user?id={user_id}")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

dp = Dispatcher(storage=MemoryStorage())

async def get_all_admin_ids() -> set[int]:
    db_admins = await get_admins()
    return set(ADMIN_IDS).union(db_admins)

# Command: /start
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    
    all_admins = await get_all_admin_ids()
    if not all_admins:
        await add_admin(message.from_user.id, message.from_user.username or "")
        logger.info(f"First user {message.from_user.id} (@{message.from_user.username}) registered as admin.")

    # If deep-linked with pilot or apply, start application directly
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    if args and args[0].lower() in ['pilot', 'apply']:
        await start_application(message, state)
        return

    text = (
        "👋 **Добро пожаловать в бота регистрации пилотных групп «РИТМ»!**\n\n"
        "«Ритм» — умный Telegram-бот, который снимает со старост учебных групп ежедневную рутину:\n"
        "• Публикует утренний дайджест с расписанием в 07:30\n"
        "• Принимает пересылки отмен от преподавателей и обновляет закреп в чате\n"
        "• Проводит перекличку за 15 минут до пары в 4 клика\n"
        "• Формирует готовую ведомость посещаемости в Excel (`/export`)\n\n"
        "🗓 **Сроки пилотного тестирования:** 20–26 ноября 2026 года.\n"
        "Для групп-участников и старост участие **бесплатно**.\n\n"
        "Нажмите кнопку ниже, чтобы подать заявку на участие вашей группы в пилоте:\n\n"
        f"_(Ваш Telegram ID: `{message.from_user.id}`)_"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_start_keyboard())

# Command: /admin
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    all_admins = await get_all_admin_ids()
    
    if not all_admins:
        await add_admin(message.from_user.id, message.from_user.username or "")
        all_admins.add(message.from_user.id)
        await message.answer("👑 Вы успешно назначены главным администратором бота! Теперь новые заявки будут приходить сюда.")

    if message.from_user.id not in all_admins:
        await message.answer("🔒 Доступ только для администраторов.")
        return

    count = await get_applications_count()
    recent = await get_recent_applications(limit=7)
    
    msg = f"📊 **Панель администратора «РИТМ»**\n\n"
    msg += f"Всего поступило заявок: **{count}**\n\n"
    
    if recent:
        msg += "**Последние заявки:**\n"
        for r in recent:
            status_emoji = "🟢 Одобрена" if r['status'] == 'approved' else ("🔴 Отклонена" if r['status'] == 'rejected' else "🟡 Ожидает")
            user_link = f"@{r['username']}" if r['username'] else f"ID `{r['user_id']}`"
            msg += f"• **#{r['id']}** [{status_emoji}] | {r['institution']}, гр. {r['group_name']} ({r['students_count']} чел.) — {r['full_name']} ({user_link})\n"
    else:
        msg += "_Заявок пока нет._"

    await message.answer(msg, parse_mode="Markdown")

# Command: /setadmin
@dp.message(Command("setadmin"))
async def cmd_setadmin(message: types.Message):
    await add_admin(message.from_user.id, message.from_user.username or "")
    await message.answer(f"✅ Пользователь `{message.from_user.id}` зарегистрирован как администратор бота.", parse_mode="Markdown")

# Command: /help
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "ℹ️ **Справка по боту регистрации «РИТМ»**\n\n"
        "Команды:\n"
        "/start — Главное меню и приветствие\n"
        "/apply — Начать заполнение анкеты на пилотный тест\n"
        "/cancel — Отменить текущее заполнение анкеты\n"
        "/about — Подробнее о проекте «Ритм»\n"
        "/admin — Панель управления заявками\n\n"
        "По всем вопросам: @spizhy"
    )
    await message.answer(text, parse_mode="Markdown")

# Command: /about
@dp.message(Command("about"))
@dp.callback_query(F.data == "action_about")
async def cmd_about(event: types.Message | types.CallbackQuery):
    text = (
        "📖 **О проекте «РИТМ»**\n\n"
        "Проект создан студентами для студентов и старост (Trepet & Jutreyk & Filthness).\n\n"
        "**Инженерные принципы:**\n"
        "1. **Без userbot-аккаунтов:** нулевой риск бана личного Telegram старосты, бот не читает личные переписки.\n"
        "2. **Обязательная премодерация:** бот парсит отмену, но отправляет в чат только после подтверждения старосты.\n"
        "3. **152-ФЗ РФ:** серверы в РФ, статус «Уважительная причина» вместо диагнозов, удаление по `/delete_me`.\n\n"
        "🌐 Сайт проекта: https://spizhy.github.io/ritm/\n"
        "Связь с организаторами: @spizhy"
    )
    if isinstance(event, types.CallbackQuery):
        await event.answer()
        await event.message.answer(text, parse_mode="Markdown", reply_markup=get_start_keyboard())
    else:
        await event.answer(text, parse_mode="Markdown", reply_markup=get_start_keyboard())

# Command: /cancel
@dp.message(Command("cancel"))
@dp.callback_query(F.data == "action_cancel")
async def cmd_cancel(event: types.Message | types.CallbackQuery, state: FSMContext):
    await state.clear()
    msg_text = "❌ Заполнение анкеты отменено. Вы можете начать заново в любой момент с помощью команды /apply."
    if isinstance(event, types.CallbackQuery):
        await event.answer("Отменено")
        await event.message.answer(msg_text, reply_markup=ReplyKeyboardRemove())
    else:
        await event.answer(msg_text, reply_markup=ReplyKeyboardRemove())

# --- Step-by-Step Questionnaire ---

@dp.message(Command("apply"))
@dp.callback_query(F.data == "action_start_apply")
@dp.callback_query(F.data == "confirm_restart")
async def start_application(event: types.Message | types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(PilotApplication.waiting_for_role)
    
    prompt = (
        "📋 **Шаг 1 из 12. Ваша роль в группе**\n\n"
        "Выберите, кем вы являетесь в учебной группе:"
    )
    if isinstance(event, types.CallbackQuery):
        await event.answer()
        await event.message.answer(prompt, parse_mode="Markdown", reply_markup=get_role_keyboard())
    else:
        await event.answer(prompt, parse_mode="Markdown", reply_markup=get_role_keyboard())

# Step 1: Role
@dp.callback_query(PilotApplication.waiting_for_role, F.data.startswith("role_"))
async def process_role(callback: types.CallbackQuery, state: FSMContext):
    role_map = {
        "role_starosta": "Староста группы",
        "role_deputy": "Заместитель старосты",
        "role_curator": "Куратор / Преподаватель",
        "role_student": "Студент-активист"
    }
    role_text = role_map.get(callback.data, "Студент группы")
    await state.update_data(role=role_text)
    await state.set_state(PilotApplication.waiting_for_name)
    
    await callback.answer()
    await callback.message.answer(
        f"Выбрано: **{role_text}**\n\n"
        "👤 **Шаг 2 из 12. Ваше имя и фамилия**\n"
        "Как к вам обращаться? Напишите ваше ФИО или Имя Фамилия:",
        parse_mode="Markdown"
    )

# Step 2: Name
@dp.message(PilotApplication.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()
    if len(full_name) < 2:
        await message.answer("Пожалуйста, введите корректное имя или ФИО:")
        return

    await state.update_data(full_name=full_name)
    await state.set_state(PilotApplication.waiting_for_institution)
    
    await message.answer(
        "🏛 **Шаг 3 из 12. Учебное заведение и город**\n"
        "Укажите название вашего вуза/колледжа и город\n"
        "*(например: МГТУ им. Баумана, Москва или СПбПУ, Санкт-Петербург)*:",
        parse_mode="Markdown"
    )

# Step 3: Institution
@dp.message(PilotApplication.waiting_for_institution)
async def process_institution(message: types.Message, state: FSMContext):
    institution = message.text.strip()
    if len(institution) < 2:
        await message.answer("Пожалуйста, укажите учебное заведение:")
        return

    await state.update_data(institution=institution)
    await state.set_state(PilotApplication.waiting_for_faculty)
    
    await message.answer(
        "📚 **Шаг 4 из 12. Факультет / Направление подготовки**\n"
        "Напишите факультет или специальность\n"
        "*(например: Факультет ИУ, Программная инженерия или Информационная безопасность)*:",
        parse_mode="Markdown"
    )

# Step 4: Faculty
@dp.message(PilotApplication.waiting_for_faculty)
async def process_faculty(message: types.Message, state: FSMContext):
    faculty = message.text.strip()
    await state.update_data(faculty=faculty)
    await state.set_state(PilotApplication.waiting_for_group)
    
    await message.answer(
        "🏷 **Шаг 5 из 12. Название группы и курс**\n"
        "Укажите точный шифр/номер группы и курс\n"
        "*(например: ЭВТ-21, 2 курс или ИУ7-31Б, 3 курс)*:",
        parse_mode="Markdown"
    )

# Step 5: Group & Course
@dp.message(PilotApplication.waiting_for_group)
async def process_group(message: types.Message, state: FSMContext):
    group_name = message.text.strip()
    if len(group_name) < 2:
        await message.answer("Пожалуйста, укажите группу:")
        return

    await state.update_data(group_name=group_name)
    await state.set_state(PilotApplication.waiting_for_count)
    
    await message.answer(
        "👥 **Шаг 6 из 12. Численность группы**\n"
        "Сколько примерно студентов учится в вашей группе? (Напишите число, например: *26*):",
        parse_mode="Markdown"
    )

# Step 6: Students Count
@dp.message(PilotApplication.waiting_for_count)
async def process_count(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        count = int(text)
        if count <= 0 or count > 200:
            raise ValueError()
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число студентов (например, 25):")
        return

    await state.update_data(students_count=count)
    await state.set_state(PilotApplication.waiting_for_chat_platform)
    
    await message.answer(
        "💬 **Шаг 7 из 12. Основной чат группы**\n"
        "Где сейчас находится главный чат вашей учебной группы для общения и объявлений?",
        reply_markup=get_chat_platform_keyboard(),
        parse_mode="Markdown"
    )

# Step 7: Chat Platform
@dp.callback_query(PilotApplication.waiting_for_chat_platform, F.data.startswith("chat_"))
async def process_chat_platform(callback: types.CallbackQuery, state: FSMContext):
    chat_map = {
        "chat_tg": "Telegram",
        "chat_vk": "ВКонтакте",
        "chat_sferum": "Сферум / MAX",
        "chat_other": "Другое (готовы создать в TG)"
    }
    chat_text = chat_map.get(callback.data, "Telegram")
    await state.update_data(chat_platform=chat_text)
    await state.set_state(PilotApplication.waiting_for_schedule_source)
    
    await callback.answer()
    await callback.message.answer(
        f"Выбрано: **{chat_text}**\n\n"
        "📅 **Шаг 8 из 12. Источник расписания**\n"
        "Откуда староста или группа сейчас берут актуальное расписание?",
        reply_markup=get_schedule_source_keyboard(),
        parse_mode="Markdown"
    )

# Step 8: Schedule Source
@dp.callback_query(PilotApplication.waiting_for_schedule_source, F.data.startswith("sch_"))
async def process_schedule_source(callback: types.CallbackQuery, state: FSMContext):
    sch_map = {
        "sch_site": "Сайт / электронное расписание вуза",
        "sch_excel": "Excel / PDF файл от диспетчерской",
        "sch_photo": "Фотография со стенда расписания",
        "sch_curator": "Куратор присылает в чат"
    }
    sch_text = sch_map.get(callback.data, "Сайт вуза")
    await state.update_data(schedule_source=sch_text)
    await state.set_state(PilotApplication.waiting_for_cancel_freq)
    
    await callback.answer()
    await callback.message.answer(
        f"Выбрано: **{sch_text}**\n\n"
        "⏱ **Шаг 9 из 12. Частота отмен и переносов пар**\n"
        "Как часто у вашей группы меняется расписание или отменяются пары?",
        reply_markup=get_cancel_freq_keyboard(),
        parse_mode="Markdown"
    )

# Step 9: Cancel Frequency
@dp.callback_query(PilotApplication.waiting_for_cancel_freq, F.data.startswith("freq_"))
async def process_cancel_freq(callback: types.CallbackQuery, state: FSMContext):
    freq_map = {
        "freq_weekly": "Каждую неделю (1–3 раза)",
        "freq_monthly": "1–2 раза в месяц",
        "freq_rare": "Редко / почти не бывает"
    }
    freq_text = freq_map.get(callback.data, "1–2 раза в месяц")
    await state.update_data(cancel_frequency=freq_text)
    await state.set_state(PilotApplication.waiting_for_cancel_channel)
    
    await callback.answer()
    await callback.message.answer(
        f"Выбрано: **{freq_text}**\n\n"
        "📢 **Шаг 10 из 12. Канал сообщений об отмене**\n"
        "Как преподаватели обычно сообщают старосте или группе об отмене?",
        reply_markup=get_cancel_channel_keyboard(),
        parse_mode="Markdown"
    )

# Step 10: Cancel Channel
@dp.callback_query(PilotApplication.waiting_for_cancel_channel, F.data.startswith("chan_"))
async def process_cancel_channel(callback: types.CallbackQuery, state: FSMContext):
    chan_map = {
        "chan_pm": "Пишут старосте в личку (TG/VK)",
        "chan_sdo": "Публикуют в СДО / на портале",
        "chan_curator": "Сообщают через куратора",
        "chan_door": "Узнаем уже у аудитории"
    }
    chan_text = chan_map.get(callback.data, "Пишут в личку")
    await state.update_data(cancel_channel=chan_text)
    await state.set_state(PilotApplication.waiting_for_curator_report)
    
    await callback.answer()
    await callback.message.answer(
        f"Выбрано: **{chan_text}**\n\n"
        "📊 **Шаг 11 из 12. Ведомость посещаемости**\n"
        "Требует ли куратор, деканат или учебная часть регулярный отчет о явке?",
        reply_markup=get_curator_report_keyboard(),
        parse_mode="Markdown"
    )

# Step 11: Curator Report
@dp.callback_query(PilotApplication.waiting_for_curator_report, F.data.startswith("rep_"))
async def process_curator_report(callback: types.CallbackQuery, state: FSMContext):
    rep_map = {
        "rep_regular": "Да, каждую неделю / месяц в Excel",
        "rep_session": "Только в конце семестра",
        "rep_self": "Нет, отмечаем для себя"
    }
    rep_text = rep_map.get(callback.data, "Для себя")
    await state.update_data(curator_report=rep_text)
    await state.set_state(PilotApplication.waiting_for_readiness)
    
    await callback.answer()
    await callback.message.answer(
        f"Выбрано: **{rep_text}**\n\n"
        "🚀 **Шаг 12 из 12. Готовность к пилоту (20–26 ноября)**\n"
        "Готова ли ваша группа протестировать бота в чате на боевой учебной неделе?",
        reply_markup=get_readiness_keyboard(),
        parse_mode="Markdown"
    )

# Step 12: Readiness
@dp.callback_query(PilotApplication.waiting_for_readiness, F.data.startswith("ready_"))
async def process_readiness(callback: types.CallbackQuery, state: FSMContext):
    ready_map = {
        "ready_yes": "Да, готовы к тесту с 20.11",
        "ready_help": "Готовы, если поможете настроить",
        "ready_questions": "Хотим сначала задать вопросы"
    }
    ready_text = ready_map.get(callback.data, "Да, готовы")
    await state.update_data(pilot_readiness=ready_text)
    await state.set_state(PilotApplication.waiting_for_contact)
    
    await callback.answer()
    await callback.message.answer(
        f"Выбрано: **{ready_text}**\n\n"
        "📱 **Финальный шаг. Контакты для связи**\n"
        "Как организаторам связаться с вами для подтверждения заявки и настройки бота?\n\n"
        "Нажмите кнопку «Поделиться контактом» или отправьте ваш @username / номер телефона текстом:",
        reply_markup=get_contact_keyboard(),
        parse_mode="Markdown"
    )

# Step 13: Contact Input
@dp.message(PilotApplication.waiting_for_contact, F.contact)
async def process_contact_button(message: types.Message, state: FSMContext):
    contact = message.contact.phone_number
    if message.from_user.username:
        contact += f" (@{message.from_user.username})"
    await finalize_application_preview(message, state, contact)

@dp.message(PilotApplication.waiting_for_contact)
async def process_contact_text(message: types.Message, state: FSMContext):
    contact = message.text.strip()
    if contact == "Введу контакт вручную":
        await message.answer("Напишите ваш @username в Telegram или номер телефона:", reply_markup=ReplyKeyboardRemove())
        return

    if message.from_user.username and f"@{message.from_user.username}" not in contact:
        contact += f" (профиль: @{message.from_user.username})"
    await finalize_application_preview(message, state, contact)

# Application Review & Confirmation Screen
async def finalize_application_preview(message: types.Message, state: FSMContext, contact: str):
    await state.update_data(contact=contact)
    data = await state.get_data()
    await state.set_state(PilotApplication.waiting_for_confirmation)

    summary = (
        "📄 **Проверьте вашу заявку на участие в пилотном тесте «РИТМ»:**\n\n"
        f"• **Роль:** {data.get('role')}\n"
        f"• **ФИО:** {data.get('full_name')}\n"
        f"• **Вуз / Колледж:** {data.get('institution')}\n"
        f"• **Факультет:** {data.get('faculty')}\n"
        f"• **Группа и курс:** {data.get('group_name')}\n"
        f"• **Студентов в группе:** {data.get('students_count')} чел.\n"
        f"• **Чат группы:** {data.get('chat_platform')}\n"
        f"• **Источник расписания:** {data.get('schedule_source')}\n"
        f"• **Частота отмен:** {data.get('cancel_frequency')}\n"
        f"• **Канал отмен:** {data.get('cancel_channel')}\n"
        f"• **Ведомость куратору:** {data.get('curator_report')}\n"
        f"• **Готовность к тесту:** {data.get('pilot_readiness')}\n"
        f"• **Контакт для связи:** {data.get('contact')}\n\n"
        "Все данные указаны верно?"
    )
    await message.answer(summary, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    await message.answer("Нажмите «Подтвердить и отправить заявку»:", reply_markup=get_confirmation_keyboard())

# Submission Handler
@dp.callback_query(PilotApplication.waiting_for_confirmation, F.data == "confirm_send")
async def process_confirmation(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    data["user_id"] = callback.from_user.id
    data["username"] = callback.from_user.username or ""

    try:
        app_id = await save_application(data)
    except Exception as e:
        logger.error(f"Error saving to database: {e}")
        await callback.answer("Ошибка при сохранении заявки. Попробуйте снова.", show_alert=True)
        err_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💬 Написать координатору (@spizhy)", url=build_contact_url("Здравствуйте! Возникла ошибка при сохранении заявки в боте «РИТМ»."))
        ]])
        await callback.message.edit_text(
            "⚠️ **Произошла техническая ошибка при сохранении заявки.**\n\n"
            "Пожалуйста, начните заново с помощью команды /apply или напишите координатору: @spizhy",
            parse_mode="Markdown",
            reply_markup=err_kb
        )
        await state.clear()
        return

    await state.clear()
    await callback.answer("Заявка успешно отправлена!")

    # Message for the applicant
    applicant_text = (
        "🎉 **Ваша заявка принята на рассмотрение!**\n\n"
        f"Номер заявки: `#{app_id}`\n\n"
        "Мы рассмотрим её в течение 24 часов. Как только организатор подтвердит заявку, "
        "вы получите автоматическое уведомление прямо здесь, в этом чате!\n\n"
        "Сроки пилота: **20–26 ноября 2026 года**.\n"
        "Координатор проекта: @spizhy"
    )
    applicant_done_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="💬 Задать вопрос координатору",
            url=build_contact_url(f"Здравствуйте! Пишу по поводу поданной заявки #{app_id} на пилот «РИТМ».")
        )
    ]])
    await callback.message.edit_text(applicant_text, parse_mode="Markdown", reply_markup=applicant_done_kb)

    # Notification for Admins with Approve/Reject Action Buttons
    admin_notification = (
        f"🚀 **НОВАЯ ЗАЯВКА НА ПИЛОТ «РИТМ» #{app_id}**\n\n"
        f"👤 **Заявитель:** {data.get('full_name')} (@{data.get('username') or 'без_юзернейма'})\n"
        f"🎓 **Роль:** {data.get('role')}\n"
        f"🏛 **Вуз/Колледж:** {data.get('institution')}\n"
        f"📚 **Факультет:** {data.get('faculty')}\n"
        f"🏷 **Группа:** {data.get('group_name')}\n"
        f"👥 **Численность:** {data.get('students_count')} чел.\n"
        f"💬 **Чат группы:** {data.get('chat_platform')}\n"
        f"📅 **Расписание:** {data.get('schedule_source')}\n"
        f"⏱ **Частота отмен:** {data.get('cancel_frequency')}\n"
        f"📢 **Канал отмен:** {data.get('cancel_channel')}\n"
        f"📊 **Ведомость куратору:** {data.get('curator_report')}\n"
        f"🚀 **Готовность:** {data.get('pilot_readiness')}\n"
        f"📱 **Контакты:** {data.get('contact')}\n"
        f"🆔 User ID: `{data.get('user_id')}`"
    )

    admin_keyboard = get_admin_action_keyboard(
        app_id=app_id,
        username=data.get('username', ''),
        user_id=data.get('user_id', 0)
    )

    all_admins = await get_all_admin_ids()
    for admin_id in all_admins:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=admin_notification,
                parse_mode="Markdown",
                reply_markup=admin_keyboard
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

# --- Admin Action Callbacks (Approve & Reject) ---

@dp.callback_query(F.data.startswith("admin_approve_"))
async def process_admin_approve(callback: types.CallbackQuery, bot: Bot):
    all_admins = await get_all_admin_ids()
    if callback.from_user.id not in all_admins:
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return

    app_id = int(callback.data.replace("admin_approve_", ""))
    await update_application_status(app_id, "approved")
    app_data = await get_application_by_id(app_id)

    admin_name = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.first_name
    await callback.answer(f"Заявка #{app_id} одобрена!")

    # Edit the admin message to reflect status
    current_text = callback.message.text or callback.message.caption or ""
    applicant_name = app_data.get('full_name', 'Заявитель') if app_data else 'Заявитель'
    applicant_uname = f"@{app_data.get('username')}" if app_data and app_data.get('username') else f"ID: {app_data.get('user_id') if app_data else 'неизвестно'}"
    updated_text = (
        current_text +
        f"\n\n✅ **ЗАЯВКА #{app_id} ОДОБРЕНА** (Одобрил: {admin_name})\n"
        f"📬 Уведомление об одобрении отправлено старосте: {applicant_name} ({applicant_uname})"
    )

    # Keep only the direct contact button if username exists
    new_kb = None
    if app_data and app_data.get("username"):
        to_starosta_msg = urllib.parse.quote(f"Здравствуйте, {app_data.get('full_name', '')}! Я координатор проекта «РИТМ» (@spizhy) по поводу вашей заявки #{app_id} на пилот.")
        new_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💬 Написать старосте в Telegram", url=f"https://t.me/{app_data['username']}?text={to_starosta_msg}")
        ]])

    try:
        await callback.message.edit_text(updated_text, parse_mode="Markdown", reply_markup=new_kb)
    except Exception as e:
        logger.error(f"Failed to edit admin message: {e}")

    # Send Notification to the Applicant
    if app_data and app_data.get("user_id"):
        applicant_notification = (
            f"🎉 **Отличные новости! Ваша заявка #{app_id} на участие в пилоте «РИТМ» одобрена!**\n\n"
            f"Группа: **{app_data.get('group_name')}** ({app_data.get('institution')})\n\n"
            "Координаторы проекта свяжутся с вами в Telegram до **20 ноября 2026 года** для подключения бота "
            "в чат группы и первичной настройки расписания.\n\n"
            "Если у вас есть срочные вопросы или предложения: @spizhy"
        )
        group_name = app_data.get('group_name', '')
        applicant_approve_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="💬 Написать координатору (@spizhy)",
                url=build_contact_url(f"Здравствуйте! Пишу по поводу проекта «РИТМ» (наша заявка #{app_id} для группы {group_name} одобрена на пилот).")
            )
        ]])
        try:
            await bot.send_message(
                chat_id=app_data["user_id"],
                text=applicant_notification,
                parse_mode="Markdown",
                reply_markup=applicant_approve_kb
            )
            logger.info(f"Approval notification sent to applicant {app_data['user_id']}")
        except Exception as e:
            logger.error(f"Failed to send approval message to applicant {app_data['user_id']}: {e}")

@dp.callback_query(F.data.startswith("admin_reject_"))
async def process_admin_reject(callback: types.CallbackQuery, bot: Bot):
    all_admins = await get_all_admin_ids()
    if callback.from_user.id not in all_admins:
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return

    app_id = int(callback.data.replace("admin_reject_", ""))
    await update_application_status(app_id, "rejected")
    app_data = await get_application_by_id(app_id)

    admin_name = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.first_name
    await callback.answer(f"Заявка #{app_id} отклонена.")

    current_text = callback.message.text or callback.message.caption or ""
    applicant_name = app_data.get('full_name', 'Заявитель') if app_data else 'Заявитель'
    applicant_uname = f"@{app_data.get('username')}" if app_data and app_data.get('username') else f"ID: {app_data.get('user_id') if app_data else 'неизвестно'}"
    updated_text = (
        current_text +
        f"\n\n❌ **ЗАЯВКА #{app_id} ОТКЛОНЕНА** (Модератор: {admin_name})\n"
        f"📬 Уведомление об отклонении отправлено заявителю: {applicant_name} ({applicant_uname})"
    )

    try:
        await callback.message.edit_text(updated_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to edit admin message: {e}")

    # Notify applicant politely
    if app_data and app_data.get("user_id"):
        rejection_notification = (
            f"Здравствуйте! Ваша заявка #{app_id} на участие в пилотном тесте «РИТМ» была рассмотрена.\n\n"
            "К сожалению, на ближайший ноябрьский пилотный поток количество слотов для групп ограничено, "
            "и группа не была включена в текущий набор.\n\n"
            "Мы сохранили ваши данные и обязательно предложим подключение на декабрьском этапе!\n"
            "Спасибо за интерес к проекту «РИТМ»!"
        )
        reject_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="💬 Написать координатору (@spizhy)",
                url=build_contact_url(f"Здравствуйте! Пишу по поводу заявки #{app_id} на пилот «РИТМ».")
            )
        ]])
        try:
            await bot.send_message(
                chat_id=app_data["user_id"],
                text=rejection_notification,
                parse_mode="Markdown",
                reply_markup=reject_kb
            )
        except Exception as e:
            logger.error(f"Failed to send rejection message to applicant: {e}")

# Healthcheck HTTP handler for Cloud PaaS (Render, Koyeb, Railway, etc.)
async def handle_health(request):
    from database import get_applications_count
    try:
        count = await get_applications_count()
    except Exception:
        count = 0
    return web.json_response({
        "status": "online",
        "bot": "Ritm_pilot_bot",
        "total_applications": count
    })

# Main entrypoint
async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not defined in environment variables or .env file!")
        return

    await init_db()
    bot = Bot(token=BOT_TOKEN)
    logger.info("Bot started successfully with expanded questionnaire and admin actions.")

    # Start lightweight HTTP server for Render/Koyeb 24/7 web service keep-alive
    try:
        port = int(os.getenv("PORT", "8080"))
        web_app = web.Application()
        web_app.router.add_get("/", handle_health)
        web_app.router.add_get("/health", handle_health)
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Healthcheck HTTP server listening on port {port}")
    except Exception as e:
        logger.warning(f"Could not start HTTP healthcheck server: {e}")

    while True:
        try:
            await dp.start_polling(bot)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot stopped by user.")
            break
        except Exception as e:
            logger.warning(f"Polling connection error ({type(e).__name__}: {e}). Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
