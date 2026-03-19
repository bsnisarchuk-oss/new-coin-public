from __future__ import annotations

from app.bot.handlers import menu, menu_insights, menu_watch_alerts


def test_menu_router_includes_split_subrouters() -> None:
    assert menu_watch_alerts.router in menu.router.sub_routers
    assert menu_insights.router in menu.router.sub_routers


def test_menu_cancel_handler_is_registered() -> None:
    message_handlers = menu.router.observers["message"].handlers
    callbacks = [handler.callback.__name__ for handler in message_handlers]
    assert "cmd_cancel" in callbacks
