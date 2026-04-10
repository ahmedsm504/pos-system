"""طاولات الطلب: عدة طاولات لكل طلب، ومنع استخدام الطاولة في أكثر من طلب نشط."""
from __future__ import annotations

from django.db.models import Prefetch


ACTIVE_ORDER_STATUSES = ('open', 'printed')


def busy_table_ids_global(exclude_order_id=None) -> set:
    """معرّفات الطاولات المرتبطة بطلب داخلي غير منتهٍ (مفتوح / قيد الانتظار)."""
    from .models import Order, OrderTable

    qs = Order.objects.filter(order_type='dine_in', status__in=ACTIVE_ORDER_STATUSES)
    if exclude_order_id:
        qs = qs.exclude(id=exclude_order_id)
    return set(
        OrderTable.objects.filter(order__in=qs).values_list('table_id', flat=True)
    )


def available_tables_qs(for_new_order=True, exclude_order_id=None):
    """طاولات نشطة غير محجوزة بطلب نشط آخر."""
    from .models import Table

    busy = busy_table_ids_global(exclude_order_id=exclude_order_id)
    qs = Table.objects.filter(is_active=True).order_by('number')
    if for_new_order and busy:
        qs = qs.exclude(id__in=busy)
    return qs


def validate_table_ids_for_new_order(table_ids) -> tuple[bool, str | None]:
    """طلب جديد: كل الطاولات يجب أن تكون متاحة وفاعلة."""
    from .models import Table

    ids = []
    for x in table_ids or []:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            return False, 'أرقام الطاولات غير صالحة'
    ids = list(dict.fromkeys(ids))
    if not ids:
        return True, None
    busy = busy_table_ids_global()
    for tid in ids:
        if tid in busy:
            return False, 'إحدى الطاولات مشغولة بطلب لم يُكمل بعد'
    if Table.objects.filter(id__in=ids, is_active=True).count() != len(ids):
        return False, 'طاولة غير موجودة أو غير نشطة'
    return True, None


def validate_table_ids_for_existing_order(order, new_table_ids) -> tuple[bool, str | None]:
    """تعديل طلب: يُسمح بالإبقاء على الطاولات الحالية؛ الطاولات الجديدة لا تتقاطع مع طلبات أخرى."""
    from .models import Table

    if order.order_type != 'dine_in':
        return True, None
    ids = []
    for x in new_table_ids or []:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            return False, 'أرقام الطاولات غير صالحة'
    ids = list(dict.fromkeys(ids))
    if not ids:
        return True, None
    current = set(order.table_links.values_list('table_id', flat=True))
    busy = busy_table_ids_global(exclude_order_id=order.id)
    for tid in ids:
        if tid not in current and tid in busy:
            return False, 'إحدى الطاولات مشغولة بطلب آخر'
    if Table.objects.filter(id__in=ids, is_active=True).count() != len(ids):
        return False, 'طاولة غير موجودة أو غير نشطة'
    return True, None


def sync_order_tables(order, table_ids) -> None:
    """يحذف الروابط القديمة ويُنشئها بالترتيب المُرسل."""
    from .models import OrderTable

    OrderTable.objects.filter(order=order).delete()
    if not table_ids:
        return
    for i, tid in enumerate(table_ids):
        tid = int(tid)
        OrderTable.objects.create(order=order, table_id=tid, sort_order=i)


def prefetch_order_tables(qs):
    from .models import OrderTable

    return qs.prefetch_related(
        Prefetch(
            'table_links',
            queryset=OrderTable.objects.select_related('table').order_by('sort_order', 'id'),
        ),
    )


def parse_table_ids_payload(data) -> list[int]:
    """من JSON: table_ids [] أو table_id مفرد (قديم)."""
    raw = data.get('table_ids')
    if raw is not None and isinstance(raw, (list, tuple)):
        out = []
        for x in raw:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return list(dict.fromkeys(out))
    one = data.get('table_id')
    if one not in (None, ''):
        try:
            return [int(one)]
        except (TypeError, ValueError):
            return []
    return []


def preview_tables_label(table_ids) -> str:
    from .models import Table

    if not table_ids:
        return 'بدون طاولة'
    rows = Table.objects.filter(id__in=table_ids).order_by('number')
    id_order = {tid: i for i, tid in enumerate(table_ids)}
    rows = sorted(rows, key=lambda t: id_order.get(t.id, 999))
    return '، '.join(str(t) for t in rows) if rows else 'بدون طاولة'
