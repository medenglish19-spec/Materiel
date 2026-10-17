old_text = b'''@router.delete("/api/maintenance/operation-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)\r\n
def api_operation_group_delete(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):\r\n
    group = db.get(MaintenanceOperationGroup, group_id)\r\n
    if group is None:\r\n
        raise HTTPException(status_code=404, detail="\xd9\x85\xd8\xac\xd9\x85\xd9\x88\xd8\xb9\xd8\xa9 \xd8\xb4\xd8\xb1\xd9\x88\xd8\xb7 \xd8\xa7\xd9\x84\xd8\xb5\xd9\x8a\xd8\xa7\xd9\x86\xd8\xa9 \xd8\xba\xd9\x8a\xd8\xb1 \xd9\x85\xd9\x88\xd8\xac\xd9\x88\xd8\xaf\xd8\xa9.")\r\n
    db.delete(group)\r\n
    try:\r\n
        db.commit()\r\n
    except Exception as exc:\r\n
        db.rollback()\r\n
        raise HTTPException(status_code=409, detail="\xd8\xaa\xd8\xb9\xd8\xb0\xd8\xb1 \xd8\xad\xd8\xb0\xd9\x81 \xd9\x85\xd8\xac\xd9\x85\xd9\x88\xd8\xb9\xd8\xa9 \xd8\xb4\xd8\xb1\xd9\x88\xd8\xb7 \xd8\xa7\xd9\x84\xd8\xb5\xd9\x8a\xd8\xa7\xd9\x86\xd8\xa9.") from exc\r\n
    return None\r\n
\r\n
@router.delete("/api/maintenance/operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)\r\n
def api_operation_delete(operation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):\r\n
    operation = db.get(MaintenanceOperation, operation_id)\r\n
    if operation is None:\r\n
        raise HTTPException(status_code=404, detail="\xd8\xb9\xd9\x85\xd9\x84\xd9\x8a\u0629 \xd8\xa7\xd9\x84\xd8\xb5\xd9\x8a\u0627\xd9\x86\xd8\xa9 \xd8\xba\xd9\x8a\xd8\xb1 \xd9\x85\xd9\x88\xd8\xac\xd9\x88\xd8\xaf\xd8\xa9.")\r\n
    if db.query(MaintenancePlanOperation.id).filter(MaintenancePlanOperation.operation_id == operation_id).first() is not None:\r\n
        raise HTTPException(status_code=409, detail="\xd9\x84\xd8\xa7 \xd9\x8a\xd9\x85\xd9\x83\xd9\x86 \xd8\xad\xd8\xb0\xd9\x81 \xd8\xa7\xd9\x84\xd8\xb9\xd9\x85\xd9\x84\xd9\x8a\u0629 \xd9\x84\xd8\xa3\xd9\x86\u0647\xd8\xa7 \xd9\x85\xd8\xb1\xd8\xaa\xd8\xa8\xd8\xb7\u0629 \xd8\xa8\xd8\xae\xd8\xb7\u0629 \xd8\xb5\xd9\x8a\u0627\xd9\x86\xd9\x8a\u0629. \xd8\xb9\xd8\xb7\u0644\u0647\xd8\xa7-\xd8\xa8\xd8\xaf\xd9\x84\xd8\xa7 \xd9\x85\xd9\x86 \xd8\xad\xd8\xb0\xd9\x81\xd9\x87\xd8\xa7.")\r\n
    if db.query(MaintenanceRecord.id).filter(MaintenanceRecord.operation_id == operation_id).first() is not None:\r\n
        raise HTTPException(status_code=409, detail="\xd9\x84\xd8\xa7 \xd9\x8a\xd9\x85\xd9\x83\xd9\x86 \xd8\xad\xd8\xb0\xd9\x81 \xd8\xa7\xd9\x84\xd8\xb9\xd9\x85\xd9\x84\xd9\x8a\u0629 \xd9\x84\xd8\xa3\xd9\x86\u0647\xd8\xa7 \xd9\x85\xd8\xb3\xd8\xaa\xd8\xae\xd8\xaf\xd9\x85\u0629 \xd9\x81\xd9\x8a \xd8\xb3\xd8\xac\xd9\x84 \xd8\xa7\xd9\x84\xd8\xb5\xd9\x8a\u0627\xd9\x86\xd9\x8a\u0629. \xd8\xb9\xd8\xb7\u0644\u0647\xd8\xa7-\xd8\xb1\xd8\xa8\xd8\xa7 \xd9\x85\xd9\x86 \xd8\xad\xd8\xb0\xd9\x81\xd9\x87\xd8\xa7.")\r\n
    db.delete(operation)\r\n
    try:\r\n
        db.commit()\r\n
    except Exception as exc:\r\n
        db.rollback()\r\n
        raise HTTPException(status_code=409, detail="\xd8\xaa\xd8\xb9\xd8\xb0\xd8\xb1 \xd8\xad\xd8\xb0\xd9\x81 \xd8\xb9\xd9\x85\xd9\x84\xd9\x8a\u0629 \xd8\xa7\xd9\x84\xd8\xb5\xd9\x8a\u0627\xd9\x86\xd8\xa9.") from exc\r\n
    return None'''

new_text = b'''@router.delete("/api/maintenance/operation-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)\r\n
def api_operation_group_delete(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):\r\n
    group = db.get(MaintenanceOperationGroup, group_id)\r\n
    if group is None:\r\n
        raise HTTPException(status_code=404, detail="\xd9\x85\xd8\xac\xd9\x85\xd9\x88\xd8\xb9\xd8\xa9 \xd8\xb4\xd8\xb1\xd9\x88\xd8\xb7 \xd8\xa7\xd9\x84\xd8\xb5\xd9\x8a\xd8\xa7\xd9\x86\xd8\xa9 \xd8\xba\xd9\x8a\xd8\xb1 \xd9\x85\xd9\x88\xd8\xac\xd9\x88\xd8\xaf\xd8\xa9.")\r\n
    db.delete(group)\r\n
    try:\r\n
        db.commit()\r\n
    except Exception as exc:\r\n
        db.rollback()\r\n
        raise HTTPException(status_code=409, detail="\xd8\xaa\xd8\xb9\xd8\xb0\xd8\xb1 \xd8\xad\xd8\xb0\xd9\x81 \xd9\x85\xd8\xac\xd9\x85\xd9\x88\xd8\xb9\xd8\xa9 \xd8\xb4\xd8\xb1\xd9\x88\xd8\xb7 \xd8\xa7\xd9\x84\xd8\xb5\xd9\x8a\xd8\xa7\xd9\x86\xd8\xa9.") from exc\r\n
    return None\r\n
\r\n
@router.get("/api/equipment/models")\r\n
def api_equipment_models(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):\r\n
    """Return all equipment models for operation-model association."""\r\n
    models = db.query(EquipmentModel).options(\r\n
        joinedload(EquipmentModel.equipment_type),\r\n
        joinedload(EquipmentModel.brand)\r\n
    ).order_by(EquipmentModel.name).all()\r\n
    return [{"id": m.id, "name": m.name, "type": m.equipment_type.name if m.equipment_type else "", "brand": m.brand.name if m.brand else ""} for m in models]\r\n
\r\n
@router.delete("/api/maintenance/operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)\r\n
def api_operation_delete(operation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):\r\n
    operation = db.get(MaintenanceOperation, operation_id)\r\n
    if operation is None:\r\n
        raise HTTPException(status_code=404, detail="\xd8\xb9\xd9\x85\xd9\x84\xd9\x8a\u0629 \xd8\xa7\xd9\x84\xd8\xb5\xd9\x8a\u0627\xd9\x86\xd8\xa9 \xd8\xba\xd9\x8a\xd8\xb1 \xd9\x85\xd9\x88\xd8\xac\xd9\x88\xd8\xaf\xd8\xa9.")\r\n
    if db.query(MaintenancePlanOperation.id).filter(MaintenancePlanOperation.operation_id == operation_id).first() is not None:\r\n
        raise HTTPException(status_code=409, detail="\xd9\x84\xd8\xa7 \xd9\x8a\xd9\x85\xd9\x83\xd9\x86 \xd8\xad\xd8\xb0\xd9\x81 \xd8\xa7\xd9\x84\xd8\xb9\xd9\x85\xd9\x84\xd9\x8a\u0629 \xd9\x84\xd8\xa3\xd9\x86\u0647\xd8\xa1 \xd9\x85\xd8\xb1\xd8\xa2\xd8\xa8\xd8\xb7\u0629 \xd8\xa8\xd8\xae\xd8\xb7\u0629 \xd8\xb5\xd9\x8a\u0627\xd9\x86\xd9\x8a\u0629. \xd8\xb9\xd8\xb7\u0644\u0647\xd8\xa1-\xd8\xa8\xd8\xaf\xd9\x84\xd8\xa7 \xd9\x85\xd9\x86 \xd8\xad\xd8\xb0\xd9\x81\xd9\x87\xd8\xa1.")\r\n
    if db.query(MaintenanceRecord.id).filter(MaintenanceRecord.operation_id == operation_id).first() is not None:\r\n
        raise HTTPException(status_code=409, detail="\xd9\x84\xd8\xa7 \xd9\x8a\xd9\x85\xd9\x83\xd9\x86 \xd8\xad\xd8\xb0\xd9\x81 \xd8\xa7\xd9\x84\xd8\xb9\xd9\x85\xd9\x84\xd9\x8a\u0629 \xd9\x84\xd8\xa3\xd9\x86\u0647\xd8\xa1 \xd9\x85\xd8\xb3\xd8\xaa\xd8\xae\xd8\xaf\xd9\x85\u0625 \xd9\x81\xd9\x8a \xd8\xb3\xd8\xac\xd9\x84 \xd8\xa7\xd9\x84\xd8\xb5\xd9\x8a\u0627\xd9\x86\xd9\x8a\u0629. \xd8\xb9\xd8\xb7\u0644\u0647\xd8\xa1-\xd8\xb1\xd8\xa8\xd8\xa7 \xd9\x85\xd9\x86 \xd8\xad\xd8\xb0\xd9\x81\xd9\x87\xd8\xa1.")\r\n
    db.delete(operation)\r\n
    try:\r\n
        db.commit()\r\n
    except Exception as exc:\r\n
        db.rollback()\r\n
        raise HTTPException(status_code=409, detail="\xd8\xaa\xd8\xb9\xd8\xb0\xd8\xb1 \xd8\xad\xd8\xb0\xd9\x81 \xd8\xb9\xd9\x85\xd9\x84\xd9\x8a\u0629 \xd8\xa7\xd9\x84\xd8\xb5\xd9\x8a\u0627\xd9\x86\xd8\xa9.") from exc\r\n
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
    idx = content.find(b'@router.delete("/api/maintenance/operation-groups/{group_id}"')
    if idx >= 0:
        print("Found at index:", idx)
        print(content[idx:idx+606])