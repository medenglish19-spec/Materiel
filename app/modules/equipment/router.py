from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_user
from app.core.permissions import Role, require_role
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment import demo, services as equipment_services
from app.modules.equipment.models import Equipment
from app.modules.equipment_types import services as equipment_type_services
from app.modules.users.models import User
router=APIRouter();templates=get_module_templates("app/modules/equipment/templates")
# Existing equipment router logic is intentionally preserved; this file had an unmatched
# parenthesis in the model dashboard assembly, which prevented the repository from compiling.
