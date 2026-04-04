"""منطق مشترك لعزل طلبات كل شيفت (من البداية حتى الإغلاق فقط)."""
from __future__ import annotations

from django.db.models import QuerySet

from .models import Order


def shift_orders_qs(
    cashier,
    shift,
    *,
    close_snapshot_at=None,
) -> QuerySet:
    """
    طلبات مطبوعة + مكتملة تخص هذا الشيفت فقط.

    - شيفت مفتوح: من start_time حتى الآن (لا حد أعلى).
    - شيفت مغلق: من start_time حتى end_time المحفوظ.
    - عند إغلاق الشيفت: مرّر close_snapshot_at=وقت الإغلاق لأن end_time لم يُحفظ بعد في الـ DB.
    """
    qs = Order.objects.filter(
        cashier=cashier,
        created_at__gte=shift.start_time,
        status__in=['printed', 'completed'],
    )
    if close_snapshot_at is not None:
        qs = qs.filter(created_at__lte=close_snapshot_at)
    elif getattr(shift, 'status', None) == 'closed' and shift.end_time:
        qs = qs.filter(created_at__lte=shift.end_time)
    return qs
