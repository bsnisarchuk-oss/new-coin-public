"""Lightweight i18n — flat string dictionary, no external dependencies.

Usage:
    from app.i18n import t, get_user_lang
    lang = get_user_lang(user.settings)
    text = t("digest.header", lang, count=5)
"""
from __future__ import annotations

from typing import Any

STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        # ── Notifier ────────────────────────────────────────────────────────
        "notifier.auto_digest": (
            "⚡ Слишком много уведомлений за последний час.\n"
            "Я автоматически включил <b>дайджест-режим</b> на 1 час — "
            "следующие события придут одним сообщением.\n"
            "Используй /digest чтобы отключить вручную."
        ),
        # ── Digest ──────────────────────────────────────────────────────────
        "digest.header": "📦 <b>Дайджест листингов</b> — {count} событий:\n",
        "digest.overflow": "\n...и ещё {count} событий. Используй /history для полного списка.",
        "digest.market_spot": "Spot",
        "digest.market_fut": "Fut",
        # ── Price alert ─────────────────────────────────────────────────────
        "alert.triggered": (
            "{arrow} <b>Ценовой алерт: {ticker}/{quote}</b>\n"
            "Биржа: {exchange}\n"
            "Цена <b>{price}</b> {sign} порог <b>{threshold}</b>"
        ),
        # ── Delisting ───────────────────────────────────────────────────────
        "delisting.message": (
            "⚠️ DELISTING: <b>{base}/{quote}</b> — {exchange} {market}\n"
            "Этот токен исчез с биржи. Проверьте свои позиции."
        ),
        "delisting.batch_header": "⚠️ <b>Делистинги ({count} токенов):</b>",
        "delisting.batch_overflow": "...и ещё {count} токенов",
        "delisting.batch_footer": "Проверьте свои позиции.",
        "delisting.market_spot": "Spot",
        "delisting.market_futures": "Futures",
        # ── Tracker ─────────────────────────────────────────────────────────
        "tracker.change": "{arrow} Изменение: {sign}{pct:.2f}% от цены листинга",
        "tracker.no_metrics": "Metrics: n/a",
        # ── Formatter (listing notification) ────────────────────────────────
        "fmt.first_seen": "First seen: {dt} UTC",
        "fmt.score_flags": "Score: {score}/100 | Flags: {flags}",
        "fmt.metrics_na": "Metrics: n/a",
        "fmt.arb_header": "💱 Цены на биржах:",
        "fmt.arb_spread": "  Арб. спред: {pct:.3f}% ({cheapest}\u2192{most_expensive})",
        "fmt.coin_header": "🪙 О монете:",
        "fmt.coin_genesis": "  Запущен: {year}",
        # ── Announcements ────────────────────────────────────────────────────
        "ann.header": "📢 <b>Анонс листинга [{source}]</b>\n",
        "ann.read_link": "🔗 <a href=\"{url}\">Читать анонс</a>",
        # ── /start ──────────────────────────────────────────────────────────
        "start.welcome_new": (
            "👋 <b>Привет!</b>\n\n"
            "Я слежу за новыми листингами на 5 крупных биржах:\n"
            "<b>Binance · Bybit · OKX · MEXC · Coinbase</b>\n\n"
            "Уведомляю первым при появлении новой монеты.\n\n"
            "Давай настроим всё за 3 шага 👇"
        ),
        "start.welcome_back": (
            "👋 С возвращением!\n\n"
            "Текущие настройки:\n"
            "• Биржи: {exchanges}\n"
            "• Рынки: {markets}\n"
            "• Только USDT: {usdt}\n"
            "• Мин. скор: {score}/100\n"
            "• Режим: {mode}"
        ),
        "start.mode_digest": "📋 дайджест",
        "start.mode_instant": "⚡ мгновенные",
        "start.menu_hint": "Используй кнопки меню ниже 👇",
        "start.settings_saved": "✅ Настройки сохранены!",
        "start.need_exchange": "Нужна хотя бы одна биржа",
        "start.need_market": "Нужен хотя бы один тип рынка",
        "start.yes": "да",
        "start.no": "нет",
        # ── Onboarding / menu ────────────────────────────────────────────────
        "onboarding.step1.text": (
            "📡 <b>Шаг 1 из 3 — Биржи</b>\n\n"
            "Отметь биржи, листинги которых хочешь получать.\n"
            "По умолчанию включены все."
        ),
        "onboarding.step2.text": (
            "📊 <b>Шаг 2 из 3 — Тип рынка</b>\n\n"
            "<b>Spot</b> — обычная покупка монеты.\n"
            "<b>Futures</b> — бессрочные контракты."
        ),
        "onboarding.step3.text": (
            "🔔 <b>Шаг 3 из 3 — Режим уведомлений</b>\n\n"
            "<b>⚡ Мгновенно</b> — уведомление сразу при обнаружении листинга.\n\n"
            "<b>📋 Дайджест</b> — сводка всех листингов раз в час.\n"
            "Удобно, если не хочешь много сообщений."
        ),
        "onboarding.continue": "Продолжить →",
        "onboarding.mode.instant": "⚡ Мгновенно",
        "onboarding.mode.digest": "📋 Дайджест раз в час",
        "onboarding.done.mode.instant": "⚡ мгновенные",
        "onboarding.done.mode.digest": "📋 дайджест раз в час",
        "onboarding.done.text": (
            "✅ <b>Готово! Всё настроено.</b>\n\n"
            "• Биржи: {exchanges}\n"
            "• Рынки: {markets}\n"
            "• Режим: {mode}\n\n"
            "Буду присылать уведомления о новых листингах.\n\n"
            "<i>⚙️ /filters — изменить настройки в любой момент\n"
            "/help — все команды</i>"
        ),
        "menu.main.watch": "👁 Слежка",
        "menu.main.alerts": "🔔 Алерты",
        "menu.main.settings": "⚙️ Настройки",
        "menu.main.analytics": "📈 Аналитика",
        "menu.main.help": "ℹ️ Помощь",
        "menu.section.watch": "👁 <b>Слежка за монетами</b>",
        "menu.section.alerts": "🔔 <b>Ценовые алерты</b>",
        "menu.section.settings": "⚙️ <b>Настройки</b>",
        "menu.section.analytics": "📈 <b>Аналитика</b>",
        "menu.section.help": "ℹ️ <b>Помощь</b>",
        "menu.watch.list": "📋 Мой список",
        "menu.watch.add": "➕ Добавить монету",
        "menu.watch.remove": "❌ Убрать монету",
        "menu.alerts.list": "📋 Мои алерты",
        "menu.alerts.add": "➕ Новый алерт",
        "menu.alerts.remove": "❌ Удалить алерт",
        "menu.settings.filters": "🔧 Фильтры",
        "menu.settings.presets": "💾 Пресеты",
        "menu.settings.pause": "⏸ Пауза",
        "menu.settings.digest": "📋 Дайджест вкл/выкл",
        "menu.analytics.stats": "📊 Статистика",
        "menu.analytics.top": "🏆 Топ 10",
        "menu.analytics.history": "📜 История",
        "menu.analytics.export": "📁 Экспорт CSV",
        "menu.help.help": "ℹ️ Справка",
        "menu.help.status": "📊 Статус",
        "menu.common.close": "✖ Закрыть",
        "menu.common.cancel": "✖ Отмена",
        "commands.start": "Зарегистрироваться в боте",
        "commands.help": "Список всех команд",
        "commands.status": "Текущие фильтры и статистика",
        "commands.filters": "Настройка фильтров",
        "commands.watch": "Добавить тикер в watchlist",
        "commands.watchlist": "Показать watchlist",
        "commands.unwatch": "Удалить тикер из watchlist",
        "commands.pause": "Пауза уведомлений (30m / 2h / 1d)",
        "commands.digest": "Дайджест-режим вкл/выкл",
        "commands.history": "История листингов",
        "commands.analytics": "Статистика по биржам",
        "commands.alert": "Ценовой алерт: /alert BTC > 100000",
        "commands.alerts": "Список активных алертов",
        "commands.unalert": "Удалить алерт по ID",
        "commands.preset": "Пресеты фильтров: save/load/list/delete",
        "commands.top": "Топ-10 листингов за 24 часа",
        "commands.export": "Экспорт листингов за 7 дней в CSV",
        "commands.setchannel": "Подключить канал для дублирования листингов",
        "commands.unsetchannel": "Отключить связанный канал",
        "commands.lang": "Язык: /lang ru | /lang en",
        # ── /help ───────────────────────────────────────────────────────────
        "help.text": (
            "Доступные команды:\n"
            "/start — регистрация\n"
            "/status — ваши фильтры и статистика\n"
            "/filters — настройка фильтров (биржи, рынки, USDT, score)\n"
            "/watch &lt;TICKER&gt; — добавить тикер в watchlist\n"
            "/watchlist — показать watchlist\n"
            "/unwatch &lt;TICKER&gt; — удалить из watchlist\n"
            "/pause &lt;30m|2h|1d&gt; — приостановить уведомления\n"
            "/pause — снять паузу досрочно\n"
            "/digest on|off — дайджест-режим (раз в час вместо мгновенных)\n"
            "/history — последние листинги\n"
            "/analytics — статистика по биржам\n"
            "/top — топ листингов за 24 часа\n"
            "/export — экспорт истории в CSV (7 дней)\n"
            "/alert &lt;TICKER&gt; &gt;|&lt; &lt;ЦЕНА&gt; — ценовой алерт\n"
            "/alerts — список активных алертов\n"
            "/unalert &lt;ID&gt; — удалить алерт\n"
            "/preset save|load|list|delete &lt;NAME&gt; — пресеты фильтров\n"
            "/setchannel &lt;ID&gt; — дублировать листинги в канал\n"
            "/unsetchannel — отключить канал\n"
            "/lang ru|en — язык интерфейса\n"
            "/help — эта справка"
        ),
        # ── /lang ───────────────────────────────────────────────────────────
        "lang.current": "Текущий язык: <b>{code}</b>\nДоступны: /lang ru  /lang en",
        "lang.changed_ru": "✅ Язык изменён на Русский 🇷🇺",
        "lang.changed_en": "✅ Language changed to English 🇬🇧",
        "lang.unknown": "Неизвестный язык. Доступны: <code>ru</code>, <code>en</code>",
        # ── Volume spike ────────────────────────────────────────────────────
        "volume_spike.alert": (
            "📊 <b>Всплеск объёма: {base}/USDT</b>\n"
            "Объём вырос в <b>{multiplier}</b> от нормы\n"
            "Текущий объём: <b>${vol}</b>"
        ),
        # ── Dispatcher ──────────────────────────────────────────────────────
        "dispatcher.rate_limit": "Слишком много запросов. Подождите немного.",
        "dispatcher.internal_error": "⚠️ Внутренняя ошибка. Попробуйте ещё раз позже.",
    },
    "en": {
        # ── Notifier ────────────────────────────────────────────────────────
        "notifier.auto_digest": (
            "⚡ Too many notifications in the last hour.\n"
            "I've automatically enabled <b>digest mode</b> for 1 hour — "
            "upcoming events will arrive as a single summary.\n"
            "Use /digest to disable manually."
        ),
        # ── Digest ──────────────────────────────────────────────────────────
        "digest.header": "📦 <b>Listing digest</b> — {count} events:\n",
        "digest.overflow": "\n...and {count} more events. Use /history for the full list.",
        "digest.market_spot": "Spot",
        "digest.market_fut": "Fut",
        # ── Price alert ─────────────────────────────────────────────────────
        "alert.triggered": (
            "{arrow} <b>Price alert: {ticker}/{quote}</b>\n"
            "Exchange: {exchange}\n"
            "Price <b>{price}</b> {sign} threshold <b>{threshold}</b>"
        ),
        # ── Delisting ───────────────────────────────────────────────────────
        "delisting.message": (
            "⚠️ DELISTING: <b>{base}/{quote}</b> — {exchange} {market}\n"
            "This token has disappeared from the exchange. Check your positions."
        ),
        "delisting.batch_header": "⚠️ <b>Delistings ({count} tokens):</b>",
        "delisting.batch_overflow": "...and {count} more tokens",
        "delisting.batch_footer": "Check your positions.",
        "delisting.market_spot": "Spot",
        "delisting.market_futures": "Futures",
        # ── Tracker ─────────────────────────────────────────────────────────
        "tracker.change": "{arrow} Change: {sign}{pct:.2f}% from listing price",
        "tracker.no_metrics": "Metrics: n/a",
        # ── Formatter ───────────────────────────────────────────────────────
        "fmt.first_seen": "First seen: {dt} UTC",
        "fmt.score_flags": "Score: {score}/100 | Flags: {flags}",
        "fmt.metrics_na": "Metrics: n/a",
        "fmt.arb_header": "💱 Prices across exchanges:",
        "fmt.arb_spread": "  Arb spread: {pct:.3f}% ({cheapest}\u2192{most_expensive})",
        "fmt.coin_header": "🪙 About the coin:",
        "fmt.coin_genesis": "  Launched: {year}",
        # ── Announcements ────────────────────────────────────────────────────
        "ann.header": "📢 <b>Listing announcement [{source}]</b>\n",
        "ann.read_link": "🔗 <a href=\"{url}\">Read announcement</a>",
        # ── /start ──────────────────────────────────────────────────────────
        "start.welcome_new": (
            "👋 <b>Hello!</b>\n\n"
            "I track new listings on 5 major exchanges:\n"
            "<b>Binance · Bybit · OKX · MEXC · Coinbase</b>\n\n"
            "Get notified first when a new coin appears.\n\n"
            "Let's set everything up in 3 steps 👇"
        ),
        "start.welcome_back": (
            "👋 Welcome back!\n\n"
            "Current settings:\n"
            "• Exchanges: {exchanges}\n"
            "• Markets: {markets}\n"
            "• USDT only: {usdt}\n"
            "• Min score: {score}/100\n"
            "• Mode: {mode}"
        ),
        "start.mode_digest": "📋 digest",
        "start.mode_instant": "⚡ instant",
        "start.menu_hint": "Use the menu buttons below 👇",
        "start.settings_saved": "✅ Settings saved!",
        "start.need_exchange": "At least one exchange required",
        "start.need_market": "At least one market type required",
        "start.yes": "yes",
        "start.no": "no",
        # ── Onboarding / menu ────────────────────────────────────────────────
        "onboarding.step1.text": (
            "📡 <b>Step 1 of 3 — Exchanges</b>\n\n"
            "Choose the exchanges you want to track.\n"
            "All of them are enabled by default."
        ),
        "onboarding.step2.text": (
            "📊 <b>Step 2 of 3 — Market type</b>\n\n"
            "<b>Spot</b> — regular spot listings.\n"
            "<b>Futures</b> — perpetual contracts."
        ),
        "onboarding.step3.text": (
            "🔔 <b>Step 3 of 3 — Notification mode</b>\n\n"
            "<b>⚡ Instant</b> — send a message as soon as a listing is detected.\n\n"
            "<b>📋 Digest</b> — send one hourly summary instead.\n"
            "Useful if you want less noise."
        ),
        "onboarding.continue": "Continue →",
        "onboarding.mode.instant": "⚡ Instant",
        "onboarding.mode.digest": "📋 Hourly digest",
        "onboarding.done.mode.instant": "⚡ instant",
        "onboarding.done.mode.digest": "📋 hourly digest",
        "onboarding.done.text": (
            "✅ <b>Done! Everything is configured.</b>\n\n"
            "• Exchanges: {exchanges}\n"
            "• Markets: {markets}\n"
            "• Mode: {mode}\n\n"
            "I'll notify you about new listings.\n\n"
            "<i>⚙️ /filters — change settings anytime\n"
            "/help — all commands</i>"
        ),
        "menu.main.watch": "👁 Watch",
        "menu.main.alerts": "🔔 Alerts",
        "menu.main.settings": "⚙️ Settings",
        "menu.main.analytics": "📈 Analytics",
        "menu.main.help": "ℹ️ Help",
        "menu.section.watch": "👁 <b>Coin watchlist</b>",
        "menu.section.alerts": "🔔 <b>Price alerts</b>",
        "menu.section.settings": "⚙️ <b>Settings</b>",
        "menu.section.analytics": "📈 <b>Analytics</b>",
        "menu.section.help": "ℹ️ <b>Help</b>",
        "menu.watch.list": "📋 My watchlist",
        "menu.watch.add": "➕ Add coin",
        "menu.watch.remove": "❌ Remove coin",
        "menu.alerts.list": "📋 My alerts",
        "menu.alerts.add": "➕ New alert",
        "menu.alerts.remove": "❌ Delete alert",
        "menu.settings.filters": "🔧 Filters",
        "menu.settings.presets": "💾 Presets",
        "menu.settings.pause": "⏸ Pause",
        "menu.settings.digest": "📋 Toggle digest",
        "menu.analytics.stats": "📊 Stats",
        "menu.analytics.top": "🏆 Top 10",
        "menu.analytics.history": "📜 History",
        "menu.analytics.export": "📁 Export CSV",
        "menu.help.help": "ℹ️ Help",
        "menu.help.status": "📊 Status",
        "menu.common.close": "✖ Close",
        "menu.common.cancel": "✖ Cancel",
        "commands.start": "Register in the bot",
        "commands.help": "List all commands",
        "commands.status": "Current filters and stats",
        "commands.filters": "Configure filters",
        "commands.watch": "Add ticker to watchlist",
        "commands.watchlist": "Show watchlist",
        "commands.unwatch": "Remove ticker from watchlist",
        "commands.pause": "Pause notifications (30m / 2h / 1d)",
        "commands.digest": "Toggle digest mode",
        "commands.history": "Listing history",
        "commands.analytics": "Exchange statistics",
        "commands.alert": "Price alert: /alert BTC > 100000",
        "commands.alerts": "List active alerts",
        "commands.unalert": "Delete alert by ID",
        "commands.preset": "Filter presets: save/load/list/delete",
        "commands.top": "Top listings over 24h",
        "commands.export": "Export listings as CSV",
        "commands.setchannel": "Link a channel for forwarding",
        "commands.unsetchannel": "Unlink the current channel",
        "commands.lang": "Language: /lang ru | /lang en",
        # ── /help ───────────────────────────────────────────────────────────
        "help.text": (
            "Available commands:\n"
            "/start — register\n"
            "/status — your filters and statistics\n"
            "/filters — configure filters (exchanges, markets, USDT, score)\n"
            "/watch &lt;TICKER&gt; — add ticker to watchlist\n"
            "/watchlist — show watchlist\n"
            "/unwatch &lt;TICKER&gt; — remove from watchlist\n"
            "/pause &lt;30m|2h|1d&gt; — pause notifications\n"
            "/pause — unpause early\n"
            "/digest on|off — digest mode (hourly summary instead of instant)\n"
            "/history — recent listings\n"
            "/analytics — exchange statistics\n"
            "/top — top listings in the last 24 hours\n"
            "/export — export history as CSV (7 days)\n"
            "/alert &lt;TICKER&gt; &gt;|&lt; &lt;PRICE&gt; — price alert\n"
            "/alerts — list active alerts\n"
            "/unalert &lt;ID&gt; — delete alert\n"
            "/preset save|load|list|delete &lt;NAME&gt; — filter presets\n"
            "/setchannel &lt;ID&gt; — duplicate listings to a channel\n"
            "/unsetchannel — disconnect channel\n"
            "/lang ru|en — interface language\n"
            "/help — this help"
        ),
        # ── /lang ───────────────────────────────────────────────────────────
        "lang.current": "Current language: <b>{code}</b>\nAvailable: /lang ru  /lang en",
        "lang.changed_ru": "✅ Язык изменён на Русский 🇷🇺",
        "lang.changed_en": "✅ Language changed to English 🇬🇧",
        "lang.unknown": "Unknown language. Available: <code>ru</code>, <code>en</code>",
        # ── Volume spike ────────────────────────────────────────────────────
        "volume_spike.alert": (
            "📊 <b>Volume spike: {base}/USDT</b>\n"
            "Volume is <b>{multiplier}</b> above normal\n"
            "Current volume: <b>${vol}</b>"
        ),
        # ── Dispatcher ──────────────────────────────────────────────────────
        "dispatcher.rate_limit": "Too many requests. Please wait a moment.",
        "dispatcher.internal_error": "⚠️ Internal error. Please try again later.",
    },
}

_SUPPORTED: frozenset[str] = frozenset(STRINGS)


def t(key: str, lang: str = "ru", **kwargs: Any) -> str:
    """Return the translated string for *key* in *lang*, falling back to Russian."""
    bucket = STRINGS.get(lang) or STRINGS["ru"]
    text = bucket.get(key) or STRINGS["ru"].get(key, key)
    return text.format(**kwargs) if kwargs else text


def get_user_lang(settings: dict | None) -> str:
    """Return language code stored in user.settings, defaulting to 'ru'."""
    lang = (settings or {}).get("lang", "ru")
    return lang if lang in _SUPPORTED else "ru"
