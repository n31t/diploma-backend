"""FSM state groups for Telegram bot (aiogram 3)."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AnalyzeFsm(StatesGroup):
    """URL expectation after user chooses Analyze URL."""

    idle = State()
    expecting_url = State()


class SettingsFsm(StatesGroup):
    """Single-screen settings flow; sub-states for inline pickers."""

    main = State()
    ui_lang = State()
    det_lang = State()
