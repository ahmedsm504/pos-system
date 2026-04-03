from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import authenticate
from django.db.models import Count, Q, Sum
import json, logging
from datetime import date
from decimal import Decimal

try:
    import requests as http_requests
except ImportError:
    http_requests = None

log = logging.getLogger(__name__)

from .models import (Category, MenuItem, Table, Waiter, DeliveryDriver,
                     Order, OrderItem, Shift, CashierProfile, InventoryEntry)


# ── Decorators ────────────────────────────────────────────────────────────────
def cashier_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.is_staff:
            return redirect('admin_dashboard')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


def get_profile(user):
    try:
        return user.cashier_profile
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════════════════════

@cashier_required
def dashboard(request):
    today = date.today()
    orders_today = Order.objects.filter(cashier=request.user, created_at__date=today)
    active_orders = Order.objects.filter(
        cashier=request.user, status__in=['open', 'printed']
    ).select_related('table', 'waiter').prefetch_related('items')

    profile = get_profile(request.user)
    shift = Shift.objects.filter(cashier=request.user, status='open').first()

    return render(request, 'pos/cashier/dashboard.html', {
        'orders_count': orders_today.count(),
        'active_orders': active_orders,
        'profile': profile,
        'shift': shift,
    })


# ══════════════════════════════════════════════════════════════════════════
#  NEW ORDER
# ══════════════════════════════════════════════════════════════════════════

@cashier_required
def new_order(request):
    categories = Category.objects.filter(is_active=True).prefetch_related('items')
    tables      = Table.objects.filter(is_active=True)
    waiters     = Waiter.objects.filter(is_active=True)
    drivers     = DeliveryDriver.objects.filter(is_active=True)
    return render(request, 'pos/cashier/new_order.html', {
        'categories': categories,
        'tables':     tables,
        'waiters':    waiters,
        'drivers':    drivers,
    })


# ══════════════════════════════════════════════════════════════════════════
#  ORDER DETAIL
# ══════════════════════════════════════════════════════════════════════════

@cashier_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related('table', 'waiter', 'driver')
                     .prefetch_related('items__menu_item__category'),
        id=order_id, cashier=request.user
    )
    categories = Category.objects.filter(is_active=True).prefetch_related('items')
    profile = get_profile(request.user)
    return render(request, 'pos/cashier/order_detail.html', {
        'order':      order,
        'categories': categories,
        'profile':    profile,
    })


@cashier_required
def orders_list(request):
    today = date.today()
    orders = Order.objects.filter(
        cashier=request.user, created_at__date=today
    ).select_related('table', 'waiter').order_by('-created_at')
    order_stats = orders.aggregate(
        total=Count('id'),
        dine_in=Count('id', filter=Q(order_type='dine_in')),
        delivery=Count('id', filter=Q(order_type='delivery')),
    )
    profile = get_profile(request.user)
    return render(request, 'pos/cashier/orders_list.html', {
        'orders':       orders,
        'order_stats':  order_stats,
        'profile':      profile,
    })


# ══════════════════════════════════════════════════════════════════════════
#  API — PREVIEW
# ══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def preview_order(request):
    try:
        data = json.loads(request.body)
        items_data = data.get('items', [])
        if not items_data:
            return JsonResponse({'success': False, 'error': 'اضف منتجات اولا'})

        preview_items = []
        total = 0
        for item_data in items_data:
            mi  = get_object_or_404(MenuItem, id=int(item_data['id']))
            qty = int(item_data.get('quantity', 1))
            sub = mi.price * qty
            total += sub
            note = (item_data.get('notes') or '')[:200]
            preview_items.append({
                'name':     mi.name,
                'qty':      qty,
                'price':    float(mi.price),
                'subtotal': float(sub),
                'cat_type': mi.category.category_type,
                'notes':    note,
            })

        table_label = 'بدون طاولة'
        if data.get('table_id'):
            try:
                table_label = str(Table.objects.get(id=data['table_id']))
            except Table.DoesNotExist:
                pass

        return JsonResponse({
            'success':       True,
            'items':         preview_items,
            'total':         float(total),
            'table':         table_label,
            'order_type':    data.get('order_type', 'dine_in'),
            'customer_name': data.get('customer_name', ''),
            'notes':         data.get('notes', ''),
            'time':          timezone.localtime(timezone.now()).strftime('%Y-%m-%d  %H:%M'),
            'cashier':       request.user.get_full_name() or request.user.username,
        })
    except Exception as e:
        log.error(f'preview_order: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
#  API — CREATE ORDER
# ══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def create_order(request):
    try:
        data = json.loads(request.body)
        items_data = data.get('items', [])
        if not items_data:
            return JsonResponse({'success': False, 'error': 'اضف منتجات اولا'})

        order_type = data.get('order_type', 'dine_in')

        if order_type == 'delivery':
            if not data.get('customer_phone') or not data.get('customer_address'):
                return JsonResponse({'success': False, 'error': 'رقم الهاتف والعنوان مطلوبان للديليفري'})

        order = Order.objects.create(
            cashier=request.user,
            order_type=order_type,
            status='open',
            notes=data.get('notes', ''),
            table_id=data.get('table_id') or None,
            waiter_id=data.get('waiter_id') or None,
            driver_id=data.get('driver_id') or None,
            customer_name=data.get('customer_name', ''),
            customer_phone=data.get('customer_phone', ''),
            customer_address=data.get('customer_address', ''),
        )

        for item_data in items_data:
            mi = get_object_or_404(MenuItem, id=int(item_data['id']))
            note = (item_data.get('notes') or '')[:200]
            OrderItem.objects.create(
                order=order,
                menu_item=mi,
                quantity=int(item_data.get('quantity', 1)),
                price=mi.price,
                notes=note,
            )

        print_ok = _send_to_printer(order, open_drawer=False)

        order.status     = 'printed'
        order.printed_at = timezone.now()
        order.save()

        return JsonResponse({'success': True, 'order_id': order.id, 'print_success': print_ok})
    except Exception as e:
        log.error(f'create_order: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
#  API — ADD ITEM
# ══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def add_item(request, order_id):
    try:
        order = get_object_or_404(Order, id=order_id)
        if order.status in ['completed', 'cancelled']:
            return JsonResponse({'success': False, 'error': 'لا يمكن التعديل على هذا الطلب'})

        data = json.loads(request.body)
        mi   = get_object_or_404(MenuItem, id=data['menu_item_id'])
        qty  = int(data.get('quantity', 1))

        existing = order.items.filter(menu_item=mi).first()
        if existing:
            existing.quantity += qty
            existing.save()
        else:
            OrderItem.objects.create(
                order=order, menu_item=mi, quantity=qty,
                price=mi.price, notes=data.get('notes', '')
            )

        return JsonResponse({'success': True, 'total': float(order.total)})
    except Exception as e:
        log.error(f'add_item: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
#  API — REMOVE ITEM (needs admin confirm if printed)
# ══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def remove_item(request, order_id):
    try:
        order = get_object_or_404(Order, id=order_id)
        data  = json.loads(request.body)
        item  = get_object_or_404(OrderItem, id=data['item_id'], order=order)

        if order.status in ['printed', 'completed']:
            admin_user = authenticate(
                request,
                username=data.get('admin_username', ''),
                password=data.get('admin_password', '')
            )
            if not admin_user or not admin_user.is_staff:
                return JsonResponse({'success': False, 'error': 'يلزم تاكيد المدير', 'need_admin': True})

        if int(data.get('qty', 1)) >= item.quantity:
            item.delete()
        else:
            item.quantity -= int(data.get('qty', 1))
            item.save()

        return JsonResponse({'success': True, 'total': float(order.total)})
    except Exception as e:
        log.error(f'remove_item: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
#  API — COMPLETE ORDER (opens drawer)
# ══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def complete_order(request, order_id):
    try:
        order = get_object_or_404(Order, id=order_id)
        if order.status == 'completed':
            return JsonResponse({'success': False, 'error': 'الطلب مكتمل بالفعل'})

        order.status       = 'completed'
        order.completed_at = timezone.now()
        order.save()

        _open_drawer()
        return JsonResponse({'success': True})
    except Exception as e:
        log.error(f'complete_order: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
#  API — CANCEL ORDER (needs admin confirm if printed)
# ══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def cancel_order(request, order_id):
    try:
        order = get_object_or_404(Order, id=order_id)

        # اقرأ الـ body بس لو في content
        data = {}
        if request.body:
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                data = {}

        if order.status == 'cancelled':
            return JsonResponse({'success': False, 'error': 'الطلب ملغي بالفعل'})

        if order.status == 'completed':
            return JsonResponse({'success': False, 'error': 'لا يمكن الغاء طلب مكتمل'})

        # الطلبات المطبوعة تحتاج تاكيد مدير
        if order.status == 'printed':
            admin_user = authenticate(
                request,
                username=data.get('admin_username', ''),
                password=data.get('admin_password', '')
            )
            if not admin_user or not admin_user.is_staff:
                return JsonResponse({'success': False, 'error': 'يلزم تاكيد المدير', 'need_admin': True})
            order.cancel_approved_by = admin_user

        order.status       = 'cancelled'
        order.cancelled_at = timezone.now()
        order.save()
        return JsonResponse({'success': True})
    except Exception as e:
        log.error(f'cancel_order: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
#  API — REPRINT
# ══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def reprint_order(request, order_id):
    try:
        order = get_object_or_404(Order, id=order_id)
        data  = {}
        if request.body:
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                data = {}
        ok = _send_to_printer(order, open_drawer=data.get('open_drawer', False))
        return JsonResponse({'success': ok})
    except Exception as e:
        log.error(f'reprint_order: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
#  API — OPEN DRAWER (needs admin confirm)
# ══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def open_drawer(request):
    try:
        data    = {}
        if request.body:
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                data = {}

        profile = get_profile(request.user)

        if not (profile and profile.can_open_drawer):
            admin_user = authenticate(
                request,
                username=data.get('admin_username', ''),
                password=data.get('admin_password', '')
            )
            if not admin_user or not admin_user.is_staff:
                return JsonResponse({'success': False, 'error': 'يلزم تاكيد المدير', 'need_admin': True})

        ok = _open_drawer()
        return JsonResponse({'success': ok})
    except Exception as e:
        log.error(f'open_drawer: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
#  CASHIER — واردات (بموافقة المدير، مرتبطة بالشيفت)
# ══════════════════════════════════════════════════════════════════════════

@cashier_required
def cashier_inventory(request):
    shift = Shift.objects.filter(cashier=request.user, status='open').first()
    entries = []
    if shift:
        entries = list(
            InventoryEntry.objects.filter(shift=shift)
            .select_related('added_by', 'recorded_by_cashier')
            .order_by('-id')[:80]
        )
    profile = get_profile(request.user)
    return render(
        request,
        'pos/cashier/inventory.html',
        {'shift': shift, 'entries': entries, 'profile': profile},
    )


@cashier_required
@require_POST
def cashier_inventory_submit(request):
    try:
        shift = Shift.objects.filter(cashier=request.user, status='open').first()
        if not shift:
            return JsonResponse({'success': False, 'error': 'لا يوجد شيفت مفتوح'})

        try:
            data = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            data = request.POST

        au = (data.get('admin_username') or '').strip()
        ap = data.get('admin_password') or ''
        admin_user = authenticate(request, username=au, password=ap)
        if not admin_user or not admin_user.is_staff:
            return JsonResponse({
                'success': False,
                'error':   'يجب إدخال حساب مدير صحيح للموافقة على الوارد',
                'need_admin': True,
            })

        name = (data.get('name') or '').strip()
        if not name:
            return JsonResponse({'success': False, 'error': 'أدخل اسم الصنف / الوصف'})

        try:
            qty = Decimal(str(data.get('quantity', '0')).replace(',', '.'))
            cost = Decimal(str(data.get('total_cost', '0')).replace(',', '.'))
        except Exception:
            return JsonResponse({'success': False, 'error': 'الكمية أو التكلفة غير صالحة'})
        if qty < 0 or cost < 0:
            return JsonResponse({'success': False, 'error': 'لا يُسمح بقيم سالبة'})

        InventoryEntry.objects.create(
            name=name,
            quantity=qty,
            unit=(data.get('unit') or '').strip(),
            total_cost=cost,
            date=timezone.localdate(),
            notes=(data.get('notes') or '').strip(),
            added_by=admin_user,
            shift=shift,
            recorded_by_cashier=request.user,
        )
        return JsonResponse({'success': True})
    except Exception as e:
        log.error(f'cashier_inventory_submit: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


def _shift_orders_total_sum(cashier, shift):
    """مجموع مبيعات الطلبات = نقد دخل الدرج (مطبوع + مكتمل منذ بداية الشيفت)."""
    orders = Order.objects.filter(
        cashier=cashier,
        created_at__gte=shift.start_time,
        status__in=['printed', 'completed'],
    )
    return sum(Decimal(str(o.total)) for o in orders)


def _shift_inventory_total(shift):
    """إجمالي مبالغ واردات الشيفت المسجّلة — يُجمع مع مجموع الطلبات في حساب المطابقة مع الدرج."""
    t = InventoryEntry.objects.filter(shift=shift).aggregate(s=Sum('total_cost'))['s']
    return Decimal(t) if t is not None else Decimal(0)


# ══════════════════════════════════════════════════════════════════════════
#  SHIFT END
# ══════════════════════════════════════════════════════════════════════════

@cashier_required
def end_shift(request):
    shift = Shift.objects.filter(cashier=request.user, status='open').first()
    orders_total = inventory_out = None
    if shift:
        orders_total = _shift_orders_total_sum(request.user, shift)
        inventory_out = _shift_inventory_total(shift)
    return render(
        request,
        'pos/cashier/end_shift.html',
        {
            'shift': shift,
            'orders_total': orders_total,
            'inventory_out': inventory_out,
        },
    )


@cashier_required
@require_POST
def submit_shift_end(request):
    try:
        shift = Shift.objects.filter(cashier=request.user, status='open').first()
        if not shift:
            return JsonResponse({'success': False, 'error': 'مفيش شيفت مفتوح'})

        cash_input = Decimal(request.POST.get('cash_in_drawer', '0'))

        orders_total = _shift_orders_total_sum(request.user, shift)
        inventory_total = _shift_inventory_total(shift)
        # مطابقة الدرج: مجمع السيستم = طلبات + واردات الشيفت؛ الفرق = الدرج الفعلي − المجمع
        sys_total = orders_total + inventory_total
        diff = cash_input - sys_total

        shift.cash_in_drawer = cash_input
        shift.system_total = sys_total
        shift.difference = diff
        shift.end_time = timezone.now()
        shift.status = 'closed'
        shift.notes = request.POST.get('notes', '')
        shift.save()

        return JsonResponse({
            'success': True,
            'orders_total': float(orders_total),
            'inventory_out': float(inventory_total),
            'system_total': float(sys_total),
            'cash_input': float(cash_input),
            'difference': float(diff),
            'status': 'زيادة' if diff > 0 else ('نقص' if diff < 0 else 'متطابق'),
        })
    except Exception as e:
        log.error(f'submit_shift_end: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
#  PRINT HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _build_main_lines(order):
    items      = order.items.select_related('menu_item__category').all()
    now_date   = timezone.localtime(order.created_at).strftime('%Y-%m-%d')
    now_time   = timezone.localtime(order.created_at).strftime('%H:%M')
    type_label = 'داخل المحل' if order.order_type == 'dine_in' else 'ديليفري'
    cashier_name = order.cashier.get_full_name() or order.cashier.username

    lines = [
        {'spacer': True, 'height': 5},
        {'text': 'فاتورة بيع', 'align': 'center', 'bold': True, 'size': 'xlarge'},
        {'divider': True, 'divider_style': 'double'},
    ]

    def _info_row(label, value):
        return {'cols': [
            {'text': str(value), 'width': 0.45, 'align': 'right'},
            {'text': label, 'width': 0.55, 'align': 'right', 'bold': True},
        ]}

    lines.append(_info_row('طلب رقم', f'#{order.id}'))
    lines.append(_info_row('النوع', type_label))

    if order.order_type == 'dine_in':
        lines.append(_info_row('الطاولة', order.table or 'بدون'))
        lines.append(_info_row('الويتر', order.waiter or '-'))
    else:
        lines.append(_info_row('العميل', order.customer_name or '-'))
        lines.append(_info_row('الهاتف', order.customer_phone or '-'))
        if order.customer_address:
            lines.append(_info_row('العنوان', order.customer_address))
        if order.driver:
            lines.append(_info_row('السائق', order.driver))

    lines.append(_info_row('التاريخ', now_date))
    lines.append(_info_row('الوقت', now_time))
    lines.append(_info_row('الكاشير', cashier_name))

    lines.append({'divider': True, 'divider_style': 'double'})

    lines.append({'cols': [
        {'text': 'الاجمالي', 'width': 0.25, 'align': 'left', 'bold': True},
        {'text': 'السعر', 'width': 0.2, 'align': 'center', 'bold': True},
        {'text': 'الكمية', 'width': 0.15, 'align': 'center', 'bold': True},
        {'text': 'الصنف', 'width': 0.4, 'align': 'right', 'bold': True},
    ], 'bold': True, 'size': 'small'})
    lines.append({'divider': True, 'divider_style': 'dashed'})

    for item in items:
        subtotal = item.subtotal
        lines.append({'cols': [
            {'text': f'{subtotal} ج', 'width': 0.25, 'align': 'left'},
            {'text': str(item.price), 'width': 0.2, 'align': 'center'},
            {'text': str(item.quantity), 'width': 0.15, 'align': 'center'},
            {'text': item.menu_item.name, 'width': 0.4, 'align': 'right'},
        ]})
        if item.notes:
            lines.append({'text': f'  * {item.notes}', 'align': 'right', 'size': 'small'})

    if order.notes:
        lines.append({'divider': True, 'divider_style': 'dashed'})
        lines.append({'text': f'ملاحظات: {order.notes}', 'align': 'right', 'size': 'small'})

    lines.append({'divider': True, 'divider_style': 'double'})

    total_val = order.total
    lines.append({'cols': [
        {'text': f'{total_val} ج', 'width': 0.5, 'align': 'left', 'bold': True},
        {'text': 'الاجمالي', 'width': 0.5, 'align': 'right', 'bold': True},
    ], 'bold': True, 'size': 'large'})

    lines.append({'divider': True, 'divider_style': 'double'})
    lines.append({'spacer': True, 'height': 8})
    lines.append({'text': 'شكرا لزيارتكم', 'align': 'center', 'bold': True})
    lines.append({'text': 'نتمنى لكم وقتا سعيدا', 'align': 'center', 'size': 'small'})
    lines.append({'spacer': True, 'height': 10})

    return lines


def _build_section_lines(order, cat_type):
    items = [
        i for i in order.items.select_related('menu_item__category').all()
        if i.menu_item.category.category_type == cat_type
    ]
    if not items:
        return []

    label = 'المطبخ' if cat_type == 'food' else 'البار'
    now_time = timezone.localtime(order.created_at).strftime('%H:%M')
    type_label = 'داخل المحل' if order.order_type == 'dine_in' else 'ديليفري'

    lines = [
        {'spacer': True, 'height': 5},
        {'text': label, 'align': 'center', 'bold': True, 'size': 'xlarge'},
        {'divider': True, 'divider_style': 'double'},
        {'cols': [
            {'text': now_time, 'width': 0.3, 'align': 'left'},
            {'text': f'طلب #{order.id}', 'width': 0.4, 'align': 'center', 'bold': True},
            {'text': type_label, 'width': 0.3, 'align': 'right'},
        ], 'bold': True},
    ]

    if order.order_type == 'dine_in' and order.table:
        lines.append({'text': f'الطاولة: {order.table}', 'align': 'center', 'bold': True})
    elif order.order_type == 'delivery' and order.customer_name:
        lines.append({'text': f'العميل: {order.customer_name}', 'align': 'center', 'bold': True})

    lines.append({'divider': True, 'divider_style': 'double'})

    for item in items:
        lines.append({'cols': [
            {'text': str(item.quantity), 'width': 0.15, 'align': 'left', 'bold': True},
            {'text': item.menu_item.name, 'width': 0.85, 'align': 'right', 'bold': True},
        ], 'size': 'large', 'bold': True})
        if item.notes:
            lines.append({'text': f'  * {item.notes}', 'align': 'right', 'bold': True})
        lines.append({'divider': True, 'divider_style': 'dashed'})

    lines.append({'spacer': True, 'height': 10})
    return lines


def _send_to_printer(order, open_drawer=False) -> bool:
    """يبعت الطلب لـ print_service ويرجع True لو نجح فعلا"""
    if not http_requests:
        log.error('مكتبة requests مش موجودة — pip install requests')
        return False

    try:
        payload = {
            'main_lines':    _build_main_lines(order),
            'kitchen_lines': _build_section_lines(order, 'food'),
            'bar_lines':     _build_section_lines(order, 'drink'),
            'open_drawer':   open_drawer,
        }
        r = http_requests.post(
            settings.PRINT_SERVICE_URL,
            json=payload,
            timeout=4
        )
        if r.status_code == 200:
            result = r.json()
            # نتأكد إن الـ print_service فعلا رجع success=True
            return result.get('success', False)
        else:
            log.error(f'Print service رجع status {r.status_code}')
            return False
    except http_requests.exceptions.ConnectionError:
        log.error(f'Print service مش شغال على {settings.PRINT_SERVICE_URL}')
        return False
    except http_requests.exceptions.Timeout:
        log.error('Print service timeout')
        return False
    except Exception as e:
        log.error(f'_send_to_printer error: {e}')
        return False


def _open_drawer() -> bool:
    """يفتح الدرج مستقل عن الطباعة"""
    if not http_requests:
        log.error('مكتبة requests مش موجودة')
        return False

    try:
        url = getattr(settings, 'PRINT_SERVICE_URL', 'http://127.0.0.1:5000/print')
        # بدّل /print بـ /drawer
        drawer_url = url.rsplit('/print', 1)[0] + '/drawer'
        r = http_requests.post(drawer_url, timeout=3)
        if r.status_code == 200:
            return r.json().get('success', False)
        return False
    except http_requests.exceptions.ConnectionError:
        log.error('Print service مش شغال — مش قادر يفتح الدرج')
        return False
    except Exception as e:
        log.error(f'_open_drawer error: {e}')
        return False