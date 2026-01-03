"""Panel utility functions for capacity checking and management."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Panel, Service, ServiceStatus


async def check_panel_capacity(db: AsyncSession, *, panel_id: int) -> tuple[bool, str | None]:
    """
    Check if panel has capacity for new config.
    
    Uses database COUNT query for accuracy (avoids sync issues with current_config_count field).
    
    Args:
        db: Database session
        panel_id: Panel ID to check
        
    Returns:
        Tuple of (has_capacity, error_message)
        - has_capacity: True if panel can accept new configs, False otherwise
        - error_message: None if has capacity, error message if at capacity
    """
    panel = await db.get(Panel, panel_id)
    if not panel:
        return False, f"Panel {panel_id} not found"
    
    # If no limit set, panel has unlimited capacity
    if panel.max_configs_per_panel is None:
        return True, None
    
    # Count active services for this panel
    res = await db.execute(
        select(func.count(Service.id)).where(
            Service.panel_id == panel_id,
            Service.status == ServiceStatus.ACTIVE,
        )
    )
    active_count = int(res.scalar() or 0)
    
    # Check if at capacity
    if active_count >= panel.max_configs_per_panel:
        return False, f"Panel {panel.name} is at capacity ({active_count}/{panel.max_configs_per_panel} configs)"
    
    return True, None


async def sync_panel_config_count(db: AsyncSession, *, panel_id: int) -> int:
    """
    Sync panel.current_config_count with actual count of active services.
    
    This is useful for admin display purposes and fixing any sync issues.
    The actual capacity checking uses COUNT queries for accuracy.
    
    Args:
        db: Database session
        panel_id: Panel ID to sync
        
    Returns:
        Updated config count
    """
    panel = await db.get(Panel, panel_id)
    if not panel:
        raise ValueError(f"Panel {panel_id} not found")
    
    # Count active services
    res = await db.execute(
        select(func.count(Service.id)).where(
            Service.panel_id == panel_id,
            Service.status == ServiceStatus.ACTIVE,
        )
    )
    actual_count = int(res.scalar() or 0)
    
    # Update panel count (for display purposes)
    panel.current_config_count = actual_count
    await db.commit()
    
    return actual_count

