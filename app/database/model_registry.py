"""Central SQLAlchemy model registry for Materiel.

Import every model-bearing module once, then configure all mappers explicitly.
This prevents first-query failures caused by partially populated registries.
"""

from sqlalchemy.orm import configure_mappers

# Core/user models must be imported before dependent modules where practical.
from app.modules.users import models as users_models  # noqa: F401
from app.modules.equipment_types import models as equipment_types_models  # noqa: F401
from app.modules.equipment import models as equipment_models  # noqa: F401
from app.modules.faults_repairs import models as faults_repairs_models  # noqa: F401
from app.modules.maintenance import models as maintenance_models  # noqa: F401
from app.modules.tires import models as tires_models  # noqa: F401
from app.modules.batteries import models as batteries_models  # noqa: F401
from app.modules.fuel import models as fuel_models  # noqa: F401
from app.modules.missions import models as missions_models  # noqa: F401
from app.modules.meter_readings import models as meter_models  # noqa: F401
from app.modules.meter_readings import batches as meter_batches  # noqa: F401
from app.modules.meter_readings import audit as meter_audit  # noqa: F401
from app.modules.meter_readings import audit_events as meter_audit_events  # noqa: F401

configure_mappers()
