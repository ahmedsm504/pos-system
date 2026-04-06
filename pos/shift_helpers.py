"""منطق مشترك لعزل طلبات كل شيفت (من البداية حتى الإغلاق فقط)."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import QuerySet
from django.utils import timezone

from .models import Order


def revenue_booked_from_shift_close(orders_total: Decimal, drawer_minus_system: Decimal) -> Decimal:
    """
    إيراد يُحسب للتقارير عند إغلاق الشيفت:
    مبيعات الطلبات (المسجّلة بالسيستم) + زيادة الدرج إن وُجدت (الفرق الموجب).
    عند العجز: لا يُضاف للمبيعات شيء (لا نخصم من رقم الإيراد).
    """
    surplus = max(Decimal('0'), drawer_minus_system)
    return orders_total + surplus


def shift_all_orders_qs(cashier, shift) -> QuerySet:
    """كل طلبات الكاشير ضمن فترة الشيفت (كل الحالات) — لسجل المراجعة."""
    qs = Order.objects.filter(
        cashier=cashier,
        created_at__gte=shift.start_time,
    )
    if getattr(shift, 'status', None) == 'closed' and shift.end_time:
        qs = qs.filter(created_at__lte=shift.end_time)
    return qs.order_by('created_at', 'id')


def build_shift_timeline(orders, inventory_entries):
    """
    ترتيب زمني معقول: لكل يوم تقويمي (بالتوقيت المحلي) —
    طلبات اليوم حسب created_at ثم واردات ذلك اليوم حسب id.
    """
    by_day = defaultdict(lambda: {'orders': [], 'inv': []})
    for o in orders:
        d = timezone.localtime(o.created_at).date()
        by_day[d]['orders'].append(o)
    for inv in inventory_entries:
        by_day[inv.date]['inv'].append(inv)
    timeline = []
    for d in sorted(by_day.keys()):
        b = by_day[d]
        for o in sorted(b['orders'], key=lambda x: (x.created_at, x.id)):
            timeline.append(('order', o))
        for inv in sorted(b['inv'], key=lambda x: x.id):
            timeline.append(('inv', inv))
    return timeline


def annotate_timeline_days(timeline):
    """يضيف show_day و day لكل عنصر لعرض شريط التاريخ مرة واحدة عند تغيّر اليوم."""
    last = None
    out = []
    for kind, obj in timeline:
        if kind == 'order':
            d = timezone.localtime(obj.created_at).date()
        else:
            d = obj.date
        show = d != last
        last = d
        out.append({'kind': kind, 'obj': obj, 'day': d, 'show_day': show})
    return out


def shift_cancelled_orders_count(
    cashier,
    shift,
    *,
    close_snapshot_at=None,
) -> int:
    """عدد الطلبات الملغاة ضمن فترة الشيفت (لا تُحسب في المبيعات)."""
    qs = Order.objects.filter(
        cashier=cashier,
        created_at__gte=shift.start_time,
        status='cancelled',
    )
    if close_snapshot_at is not None:
        qs = qs.filter(created_at__lte=close_snapshot_at)
    elif getattr(shift, 'status', None) == 'closed' and shift.end_time:
        qs = qs.filter(created_at__lte=shift.end_time)
    return qs.count()


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
