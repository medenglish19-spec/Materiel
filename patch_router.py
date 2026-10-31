old_text = '''@router.delete("/api/maintenance/operation-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_operation_group_delete(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    group = db.get(MaintenanceOperationGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="مجموعة شروط الصيانة غير موجودة.")
    db.delete(group)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر حذف مجموعة شروط الصيانة.") from exc
    return None


@router.delete("/api/maintenance/operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_operation_delete(operation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    operation = db.get(MaintenanceOperation, operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    if db.query(MaintenancePlanOperation.id).filter(MaintenancePlanOperation.operation_id == operation_id).first() is not None:
        raise HTTPException(status_code=409, detail="لا يمكن حذف العملية لأنها مرتبطة بخطة صيانة. عطّلها بدلًا من حذفها.")
    if db.query(MaintenanceRecord.id).filter(MaintenanceRecord.operation_id == operation_id).first() is not None:
        raise HTTPException(status_code=409, detail="لا يمكن حذف العملية لأنها مستخدمة في سجل الصيانة. عطّلها بدلًا من حذفها.")
    db.delete(operation)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر حذف عملية الصيانة.") from exc
    return None'''

new_text = '''@router.delete("/api/maintenance/operation-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_operation_group_delete(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    group = db.get(MaintenanceOperationGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="مجموعة شروط الصيانة غير موجودة.")
    db.delete(group)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر حذف مجموعة شروط الصيانة.") from exc
    return None


@router.get("/api/equipment/models")
def api_equipment_models(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Return all equipment models for operation-model association."""
    models = db.query(EquipmentModel).options(
        joinedload(EquipmentModel.equipment_type),
        joinedload(EquipmentModel.brand)
    ).order_by(EquipmentModel.name).all()
    return [{"id": m.id, "name": m.name, "type": m.equipment_type.name if m.equipment_type else "", "brand": m.brand.name if m.brand else ""} for m in models]


@router.delete("/api/maintenance/operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_operation_delete(operation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    operation = db.get(MaintenanceOperation, operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    if db.query(MaintenancePlanOperation.id).filter(MaintenancePlanOperation.operation_id == operation_id).first() is not None:
        raise HTTPException(status_code=409, detail="لا يمكن حذف العملية لأنها مرتبطة بخطة صيانة. عطّلها بدلًا من حذفها.")
    if db.query(MaintenanceRecord.id).filter(MaintenanceRecord.operation_id == operation_id).first() is not None:
        raise HTTPException(status_code=409, detail="لا يمكن حذف العملية لأنها مستخدمة في سجل الصيانة. عطّلها بدلًا من حذفها.")
    db.delete(operation)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر حذف عملية الصيانة.") from exc
    return None'''

with open('app/modules/maintenance/router.py', 'r', encoding='utf-8') as f:
    content = f.read()

if old_text in content:
    content = content.replace(old_text, new_text)
    with open('app/modules/maintenance/router.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Replacement successful!")
else:
    print("Old text not found!")