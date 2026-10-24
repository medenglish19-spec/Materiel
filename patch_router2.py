old_text = b'''@router.delete("/api/maintenance/operation-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)\r
def api_operation_group_delete(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):\r
    group = db.get(MaintenanceOperationGroup, group_id)\r
    if group is None:\r
        raise HTTPException(status_code=404, detail="\u0645\u062c\u0645\u0648\u0639\u0629 \u0634\u0631\u0648\u0637 \u0627\u0644\u0635\u064a\u0627\u0646\u0629 \u063a\u064a\u0631 \u0645\u0648\u062c\u0648\u062f\u0629.")\r
    db.delete(group)\r
    try:\r
        db.commit()\r
    except Exception as exc:\r
        db.rollback()\r
        raise HTTPException(status_code=409, detail="\u062a\u0639\u0630\u0631 \u062d\u0630\u0641 \u0645\u062c\u0645\u0648\u0639\u0629 \u0634\u0631\u0648\u0637 \u0627\u0644\u0635\u064a\u0627\u0646\u0629.") from exc\r
    return None\r
\r
\r
@router.delete("/api/maintenance/operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)\r
def api_operation_delete(operation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):\r
    operation = db.get(MaintenanceOperation, operation_id)\r
    if operation is None:\r
        raise HTTPException(status_code=404, detail="\u0639\u0645\u0644\u064a\u0629 \u0627\u0644\u0635\u064a\u0627\u0646\u0629 \u063a\u064a\u0631 \u0645\u0648\u062c\u0648\u062f\u0629.")\r
    if db.query(MaintenancePlanOperation.id).filter(MaintenancePlanOperation.operation_id == operation_id).first() is not None:\r
        raise HTTPException(status_code=409, detail="\u0644\u0627 \u064a\u0645\u0643\u0646 \u062d\u0630\u0641 \u0627\u0644\u0639\u0645\u0644\u064a\u0629 \u0644\u0623\u0646\u0647\u0627 \u0645\u0631\u062a\u0628\u0637\u0629 \u0628\u062e\u0637\u0629 \u0635\u064a\u0627\u0646\u0629. \u0639\u0637\u0644\u0647\u0627-\u0628\u062f\u0644\u0627 \u0645\u0646 \u062d\u0630\u0641\u0647\u0627.")\r
    if db.query(MaintenanceRecord.id).filter(MaintenanceRecord.operation_id == operation_id).first() is not None:\r
        raise HTTPException(status_code=409, detail="\u0644\u0627 \u064a\u0645\u0643\u0646 \u062d\u0630\u0641 \u0627\u0644\u0639\u0645\u0644\u064a\u0629 \u0644\u0623\u0646\u0647\u0627 \u0645\u0633\u062a\u062e\u062f\u0645\u0629 \u0641\u064a \u0633\u062c\u0644 \u0627\u0644\u0635\u064a\u0627\u0646\u0629. \u0639\u0637\u0644\u0647\u0627-\u0628\u062f\u0644\u0627 \u0645\u0646 \u062d\u0630\u0641\u0647\u0627.")\r
    db.delete(operation)\r
    try:\r
        db.commit()\r
    except Exception as exc:\r
        db.rollback()\r
        raise HTTPException(status_code=409, detail="\u062a\u0639\u0630\u0631 \u062d\u0630\u0641 \u0639\u0645\u0644\u064a\u0629 \u0627\u0644\u0635\u064a\u0627\u0646\u0629.") from exc\r
    return None'''

new_text = b'''@router.delete("/api/maintenance/operation-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)\r
def api_operation_group_delete(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):\r
    group = db.get(MaintenanceOperationGroup, group_id)\r
    if group is None:\r
        raise HTTPException(status_code=404, detail="\u0645\u062c\u0645\u0648\u0639\u0629 \u0634\u0631\u0648\u0637 \u0627\u0644\u0635\u064a\u0627\u0646\u0629 \u063a\u064a\u0631 \u0645\u0648\u062c\u0648\u062f\u0629.")\r
    db.delete(group)\r
    try:\r
        db.commit()\r
    except Exception as exc:\r
        db.rollback()\r
        raise HTTPException(status_code=409, detail="\u062a\u0639\u0630\u0631 \u062d\u0630\u0641 \u0645\u062c\u0645\u0648\u0639\u0629 \u0634\u0631\u0648\u0637 \u0627\u0644\u0635\u064a\u0627\u0646\u0629.") from exc\r
    return None\r
\r
\r
@router.get("/api/equipment/models")\r
def api_equipment_models(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):\r
    """Return all equipment models for operation-model association."""\r
    models = db.query(EquipmentModel).options(\r
        joinedload(EquipmentModel.equipment_type),\r
        joinedload(EquipmentModel.brand)\r
    ).order_by(EquipmentModel.name).all()\r
    return [{"id": m.id, "name": m.name, "type": m.equipment_type.name if m.equipment_type else "", "brand": m.brand.name if m.brand else ""} for m in models]\r
\r
\r
@router.delete("/api/maintenance/operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)\r
def api_operation_delete(operation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):\r
    operation = db.get(MaintenanceOperation, operation_id)\r
    if operation is None:\r
        raise HTTPException(status_code=404, detail="\u0639\u0645\u0644\u064a\u0629 \u0627\u0644\u0635\u064a\u0627\u0646\u0629 \u063a\u064a\u0631 \u0645\u0648\u062c\u0648\u062f\u0629.")\r
    if db.query(MaintenancePlanOperation.id).filter(MaintenancePlanOperation.operation_id == operation_id).first() is not None:\r
        raise HTTPException(status_code=409, detail="\u0644\u0627 \u064a\u0645\u0643\u0646 \u062d\u0630\u0641 \u0627\u0644\u0639\u0645\u0644\u064a\u0629 \u0644\u0623\u0646\u0647\u0627 \u0645\u0631\u062a\u0628\u0637\u0629 \u0628\u062e\u0637\u0629 \u0635\u064a\u0627\u0646\u0629. \u0639\u0637\u0644\u0647\u0627-\u0628\u062f\u0644\u0627 \u0645\u0646 \u062d\u0630\u0641\u0647\u0627.")\r
    if db.query(MaintenanceRecord.id).filter(MaintenanceRecord.operation_id == operation_id).first() is not None:\r
        raise HTTPException(status_code=409, detail="\u0644\u0627 \u064a\u0645\u0643\u0646 \u062d\u0630\u0641 \u0627\u0644\u0639\u0645\u0644\u064a\u0629 \u0644\u0623\u0646\u0647\u0627 \u0645\u0633\u062a\u062e\u062f\u0645\u0629 \u0641\u064a \u0633\u062c\u0644 \u0627\u0644\u0635\u064a\u0627\u0646\u0629. \u0639\u0637\u0644\u0647\u0627-\u0628\u062f\u0644\u0627 \u0645\u0646 \u062d\u0630\u0641\u0647\u0627.")\r
    db.delete(operation)\r
    try:\r
        db.commit()\r
    except Exception as exc:\r
        db.rollback()\r
        raise HTTPException(status_code=409, detail="\u062a\u0639\u0630\u0631 \u062d\u0630\u0641 \u0639\u0645\u0644\u064a\u0629 \u0627\u0644\u0635\u064a\u0627\u0646\u0629.") from exc\r
    return None'''

with open('app/modules/maintenance/router.py', 'rb') as f:
    content = f.read()

if old_text in content:
    content = content.replace(old_text, new_text)
    with open('app/modules/maintenance/router.py', 'wb') as f:
        f.write(content)
    print("Replacement successful!")
else:
    print("Old text not found!")
    # Find what we have
    idx = content.find(b'@router.delete("/api/maintenance/operation-groups/{group_id}"')
    if idx >= 0:
        print("Found at index:", idx)
        print(content[idx:idx+606])