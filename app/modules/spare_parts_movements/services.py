    if not received_request_item_id:
        return Decimal("0")
    q = db.query(SparePartMovementItem.quantity).join(SparePartMovementDocument).filter(
        SparePartMovementDocument.document_type == "return",
        SparePartMovementItem.received_request_item_id == received_request_item_id,
    )
    if exclude:
        q = q.filter(SparePartMovementDocument.id != exclude)
    return _sum([x[0] for x in q.all()])


def _returned_total_by_distribution_item(db, distribution_item_id, exclude=None):
    q = db.query(SparePartMovementItem.quantity).join(SparePartMovementDocument).filter(
        SparePartMovementDocument.document_type == "return",
        SparePartMovementItem.source_item_id == distribution_item_id,
    )
    if exclude:
        q = q.filter(SparePartMovementDocument.id != exclude)
    return _sum([x[0] for x in q.all()])


def returnable_quantity(db, distribution_item, exclude=None):
    """الكمية القابلة للإرجاع = أصغر رصيد بين الاستلام والتوزيع.

    received_request_item_id يحدد مصدر الاستلام الحقيقي، بينما source_item_id
    يحدد بند التوزيع الذي خرجت منه الكمية. السجلات القديمة التي لا تحمل
    received_request_item_id تستعمل request_item_id كمسار توافق.
    """
    if not distribution_item:
        return Decimal("0")
    received_item_id = getattr(distribution_item, "received_request_item_id", None) or distribution_item.request_item_id
    received_item = db.query(SparePartRequestItem).filter(
        SparePartRequestItem.id == received_item_id
    ).first()
    if received_item is None:
        return Decimal("0")

    remaining_received = (
        Decimal(str(received_item.received_quantity or 0))
        - _returned_total_by_received_item(db, received_item_id, exclude)
    )
    # الإرجاع يُنسب إلى بند التوزيع للتتبع، لكن كمية الإرجاع لا تُعامل
    # كبند مستقل: السقف الحقيقي هو الرصيد المتبقي من الاستلام بعد مجموع
    # الإرجاعات، مع عدم تجاوز مجموع ما خرج من الاستلام بالتوزيع.
    distributed_total = _distribution_total(db, received_item_id, exclude)
    returned_total = _returned_total_by_received_item(db, received_item_id, exclude)
    remaining_distributed = _at_least_zero(distributed_total - returned_total)
    return _at_least_zero(min(remaining_received, remaining_distributed))
def _status(received, distributed, returned):
    """الحالة مشتقّة من الأرصدة نفسها، لا من حقل حالة يدوي.

    الترتيب هنا هو الترتيب الأكثر تحديداً أولاً: متى تداخلت حالتان انطبقت
    الأدق. مثال: بند استُلم 10 ووُزّع 3 رُجع منها 1، فينطبق «موزع جزئيًا»
    (0 < 3 < 10) و«جزء متبقٍ لدى الجهة» (0 < 1 < 3) معاً؛ والثانية أدق لأنها
    تذكر الإرجاع الذي لا تذكره الأولى.

      1. مرتجع بالكامل  → رُدّ كل ما وُزّع
      2. جزء متبقٍ       → إرجاع جزئي: 0 < رُجع < وُزّع
      3. موزع بالكامل   → وُزّع كل ما استُلم ولا إرجاع
      4. موزع جزئيًا     → 0 < وُزّع < استُلم
      5. لم يوزع         → لم يُوزّع شيء
    """
    if received <= 0 or distributed <= 0: