from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import desc, event, select
from sqlalchemy.orm import Session

from app.database.base import Base
from app.shared.mixins import TimestampMixin

# Keep the remainder of this file unchanged; targeted tuple-row compatibility
# is applied in _validate_record below.

