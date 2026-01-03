"""
Dynamic Configuration Manager - Cached, DB-backed settings.

Usage:
    from services.config_manager import config
    
    # Get a setting (cached)
    margin = await config.get("pricing.profit_margin", default=10)
    
    # Set a setting (updates DB + cache)
    await config.set("pricing.profit_margin", 15, updated_by=admin_id)
    
    # Get all in category
    ai_settings = await config.get_category("ai")
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.app_setting import AppSetting, SettingCategory, SettingType
from database.session import get_db


class ConfigManager:
    """
    Singleton configuration manager with in-memory caching.
    
    - Loads all settings on first access
    - Updates cache immediately on set()
    - Optional TTL-based cache refresh
    """
    
    _instance: ConfigManager | None = None
    _cache: dict[str, Any] = {}
    _settings_meta: dict[str, AppSetting] = {}
    _loaded: bool = False
    _lock: asyncio.Lock | None = None
    _last_refresh: datetime | None = None
    _cache_ttl: timedelta = timedelta(minutes=5)
    
    def __new__(cls) -> ConfigManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @property
    def lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock
    
    async def _load_all(self, db: AsyncSession) -> None:
        """Load all settings from DB into cache."""
        async with self.lock:
            result = await db.execute(select(AppSetting))
            settings = result.scalars().all()
            
            self._cache.clear()
            self._settings_meta.clear()
            
            for setting in settings:
                self._cache[setting.key] = setting.get_typed_value()
                self._settings_meta[setting.key] = setting
            
            self._loaded = True
            self._last_refresh = datetime.now()
            logger.debug(f"ConfigManager loaded {len(settings)} settings")
    
    async def _ensure_loaded(self, db: AsyncSession) -> None:
        """Ensure cache is populated, refresh if stale."""
        needs_refresh = (
            not self._loaded
            or self._last_refresh is None
            or datetime.now() - self._last_refresh > self._cache_ttl
        )
        if needs_refresh:
            await self._load_all(db)
    
    async def get(
        self,
        key: str,
        default: Any = None,
        *,
        db: AsyncSession | None = None,
    ) -> Any:
        """
        Get a setting value by key.
        
        Args:
            key: Setting key (e.g., "pricing.profit_margin")
            default: Default if not found
            db: Optional session (creates new if not provided)
            
        Returns:
            Typed value from cache
        """
        if db:
            await self._ensure_loaded(db)
            return self._cache.get(key, default)
        
        async for session in get_db():
            await self._ensure_loaded(session)
            return self._cache.get(key, default)
        
        return default
    
    async def get_bool(self, key: str, default: bool = False) -> bool:
        """Get a boolean setting."""
        value = await self.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)
    
    async def get_int(self, key: str, default: int = 0) -> int:
        """Get an integer setting."""
        value = await self.get(key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    async def get_list(self, key: str, default: list | None = None) -> list:
        """Get a list setting."""
        value = await self.get(key, default or [])
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return default or []
    
    async def set(
        self,
        key: str,
        value: Any,
        *,
        updated_by: int | None = None,
        db: AsyncSession | None = None,
    ) -> bool:
        """
        Set a setting value.
        
        Updates both DB and cache immediately (hot reload).
        
        Args:
            key: Setting key
            value: New value
            updated_by: Telegram user ID of admin
            db: Optional session
            
        Returns:
            True if updated, False if key doesn't exist
        """
        async def _do_set(session: AsyncSession) -> bool:
            setting = await session.get(AppSetting, key)
            if not setting:
                logger.warning(f"Setting not found: {key}")
                return False
            
            # Validate
            is_valid, error = setting.validate(value)
            if not is_valid:
                logger.warning(f"Invalid value for {key}: {error}")
                return False
            
            # Update
            setting.set_typed_value(value)
            setting.updated_by = updated_by
            await session.commit()
            
            # Update cache
            self._cache[key] = setting.get_typed_value()
            self._settings_meta[key] = setting
            
            logger.info(f"Setting updated: {key} = {setting.display_value}")
            return True
        
        if db:
            return await _do_set(db)
        
        async for session in get_db():
            return await _do_set(session)
        
        return False
    
    async def create(
        self,
        key: str,
        value: Any,
        *,
        setting_type: str = "string",
        category: str = "system",
        description: str = "",
        is_sensitive: bool = False,
        db: AsyncSession | None = None,
    ) -> AppSetting:
        """
        Create a new setting.
        
        Used by migrations/seed scripts.
        """
        async def _do_create(session: AsyncSession) -> AppSetting:
            setting = AppSetting(
                key=key,
                value="",
                setting_type=setting_type,
                category=category,
                description=description,
                is_sensitive=is_sensitive,
                default_value=str(value),
            )
            setting.set_typed_value(value)
            
            session.add(setting)
            await session.commit()
            await session.refresh(setting)
            
            # Update cache
            self._cache[key] = setting.get_typed_value()
            self._settings_meta[key] = setting
            
            return setting
        
        if db:
            return await _do_create(db)
        
        async for session in get_db():
            return await _do_create(session)
        
        raise RuntimeError("Failed to create setting")
    
    async def get_category(
        self,
        category: str,
        *,
        db: AsyncSession | None = None,
    ) -> list[AppSetting]:
        """Get all settings in a category."""
        async def _do_get(session: AsyncSession) -> list[AppSetting]:
            await self._ensure_loaded(session)
            return [
                s for s in self._settings_meta.values()
                if s.category == category or category in s.category
            ]
        
        if db:
            return await _do_get(db)
        
        async for session in get_db():
            return await _do_get(session)
        
        return []
    
    async def get_all(
        self,
        *,
        db: AsyncSession | None = None,
    ) -> list[AppSetting]:
        """Get all settings."""
        async def _do_get(session: AsyncSession) -> list[AppSetting]:
            await self._ensure_loaded(session)
            return list(self._settings_meta.values())
        
        if db:
            return await _do_get(db)
        
        async for session in get_db():
            return await _do_get(session)
        
        return []
    
    async def search(
        self,
        query: str,
        *,
        db: AsyncSession | None = None,
    ) -> list[AppSetting]:
        """Search settings by key or description."""
        query_lower = query.lower()
        
        async def _do_search(session: AsyncSession) -> list[AppSetting]:
            await self._ensure_loaded(session)
            return [
                s for s in self._settings_meta.values()
                if query_lower in s.key.lower() or query_lower in s.description.lower()
            ]
        
        if db:
            return await _do_search(db)
        
        async for session in get_db():
            return await _do_search(session)
        
        return []
    
    async def toggle(
        self,
        key: str,
        *,
        updated_by: int | None = None,
        db: AsyncSession | None = None,
    ) -> bool | None:
        """Toggle a boolean setting. Returns new value or None if not bool."""
        async def _do_toggle(session: AsyncSession) -> bool | None:
            setting = await session.get(AppSetting, key)
            if not setting or setting.setting_type != "bool":
                return None
            
            current = setting.get_typed_value()
            new_value = not current
            setting.set_typed_value(new_value)
            setting.updated_by = updated_by
            await session.commit()
            
            self._cache[key] = new_value
            self._settings_meta[key] = setting
            
            return new_value
        
        if db:
            return await _do_toggle(db)
        
        async for session in get_db():
            return await _do_toggle(session)
        
        return None
    
    async def reset_to_default(
        self,
        key: str,
        *,
        updated_by: int | None = None,
        db: AsyncSession | None = None,
    ) -> bool:
        """Reset a setting to its default value."""
        async def _do_reset(session: AsyncSession) -> bool:
            setting = await session.get(AppSetting, key)
            if not setting or not setting.default_value:
                return False
            
            setting.value = setting.default_value
            setting.updated_by = updated_by
            await session.commit()
            
            self._cache[key] = setting.get_typed_value()
            self._settings_meta[key] = setting
            
            return True
        
        if db:
            return await _do_reset(db)
        
        async for session in get_db():
            return await _do_reset(session)
        
        return False
    
    def invalidate_cache(self) -> None:
        """Force cache refresh on next access."""
        self._loaded = False
        self._last_refresh = None


# Global singleton
config = ConfigManager()
