"""Bootstrap/seed data for first-run deployments."""

from __future__ import annotations

import json
from datetime import datetime

from loguru import logger
from sqlalchemy import func, select

from config.settings import settings
from database.models import Panel, PanelStatus, Product, ProductStatus
from database.session import AsyncSessionLocal


async def bootstrap_seed_data() -> None:
    """
    Ensure the bot has at least one Panel + one Product so the UI isn't empty.

    This keeps initial setup "auto" (Mirza-style) without needing a separate admin panel first.
    """
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Panel))
        panel = res.scalars().first()

        if not panel:
            # Store PasarGuard-specific metadata inside config_template (no schema changes)
            config_template = json.dumps({"provider": "pasarguard_db", "inbound_tag": "SUSH"})
            panel = Panel(
                name="PasarGuard-SUSH",
                api_url=settings.pasarguard_api_url,
                api_key="db",
                node_id=settings.pasarguard_node_id,
                status=PanelStatus.ACTIVE,
                default_protocol=settings.pasarguard_default_protocol,
                default_port=settings.pasarguard_default_port,
                config_template=config_template,
                notes=f"Auto-seeded at {datetime.utcnow().isoformat()}Z",
            )
            db.add(panel)
            await db.commit()
            await db.refresh(panel)
            logger.info(f"Seeded default Panel: {panel.name} (id={panel.id})")

        res = await db.execute(select(Product))
        product = res.scalars().first()
        # Seed multiple default plans only if DB looks "empty-ish" (single auto product)
        res = await db.execute(select(func.count()).select_from(Product))
        cnt = int(res.scalar() or 0)
        should_seed_plans = cnt == 0 or (
            cnt == 1 and product and "Auto" in (product.name or "") and int(product.price) == 0
        )
        if should_seed_plans:
            # Delete all existing products first (including free ones)
            await db.execute(Product.__table__.delete())
            await db.commit()
            logger.info("Deleted old products (including free/unlimited).")

            # Seed only paid plans
            plans = [
                ("50 گیگ ماهانه - دوکاربره", 65_000, 30, 50, False, 10),
                ("100 گیگ ماهانه - دوکاربره", 130_000, 30, 100, False, 20),
                ("نامحدود - دوکاربره", 250_000, 30, 0, True, 30),
            ]
            for name, price, days, gb, is_unlimited, sort in plans:
                db.add(
                    Product(
                        panel_id=panel.id,
                        name=name,
                        description="VLESS Reality (SUSH).",
                        status=ProductStatus.ACTIVE,
                        price=price,
                        currency="IRR",
                        duration_days=days,
                        traffic_gb=gb,
                        protocol="vless",
                        stock_quantity=None,
                        auto_send_config=True,
                        is_featured=True,
                        sort_order=sort,
                        is_unlimited=is_unlimited,
                    )
                )
            await db.commit()
            logger.info("Seeded default plans (multiple products).")
