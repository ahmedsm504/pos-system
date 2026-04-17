from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.urls import reverse
import json
import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
try:
    import requests as http_requests
except ImportError:
    http_requests = None

log = logging.getLogger(__name__)


def _fmt12(dt):
    """تحويل datetime إلى نص وقت 12 ساعة بالعربي: مثال 08:30 م"""
    local = timezone.localtime(dt)
    h = local.hour
    period = 'ص' if h < 12 else 'م'
    h12 = h % 12 or 12
    return f'{h12}:{local.minute:02d} {period}'


def _fmt12_raw(dt):
    """مثل _fmt12 لكن بدون تحويل localtime (الدخل localtime بالفعل)."""
    h = dt.hour
    period = 'ص' if h < 12 else 'م'
    h12 = h % 12 or 12
    return f'{h12}:{dt.minute:02d} {period}'


def _log_activity(order, action, description='', user=None):
    try:
        OrderActivity.objects.create(order=order, action=action, description=description[:500], user=user)
    except Exception:
        pass


from .shift_helpers import (
    revenue_booked_from_shift_close,
    shift_cancelled_orders_count,
    shift_orders_qs,
)
from .models import (
    Category,
    MenuItem,
    MenuItemSize,
    Table,
    Waiter,
    DeliveryDriver,
    DeliveryCustomer,
    Order,
    OrderActivity,
    OrderItem,
    Shift,
    CashierProfile,
    InventoryEntry,
    CategoryAddon,
    DrinkOptionPreset,
)
from .menu_helpers import (
    apply_meta_to_order_item,
    compute_order_item_unit_price,
    menu_catalog_payload,
    merge_key_from_oi,
    merge_key_from_payload,
    order_item_display_name,
    order_item_print_notes,
)
from .order_table_utils import (
    available_tables_qs,
    busy_table_ids_global,
    parse_table_ids_payload,
    prefetch_order_tables,
    preview_tables_label,
    sync_order_tables,
    validate_table_ids_for_existing_order,
    validate_table_ids_for_new_order,
)


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
    profile = get_profile(request.user)
    shift = Shift.objects.filter(cashier=request.user, status='open').first()

    if shift:
        shift_orders = Order.objects.filter(cashier=request.user, shift=shift)
        active_orders = prefetch_order_tables(
            shift_orders.filter(status__in=['open', 'printed'])
            .select_related('waiter')
            .prefetch_related('items')
        )
        orders_count = shift_orders.count()
    else:
        active_orders = Order.objects.none()
        orders_count = 0

    return render(request, 'pos/cashier/dashboard.html', {
        'orders_count': orders_count,
        'active_orders': active_orders,
        'profile': profile,
        'shift': shift,
    })


# ══════════════════════════════════════════════════════════════════════════
#  NEW ORDER
# ══════════════════════════════════════════════════════════════════════════

def _cashier_menu_queryset():
    return (
        Category.objects.filter(is_active=True)
        .order_by('order', 'name')
        .prefetch_related(
            Prefetch(
                'addons',
                queryset=CategoryAddon.objects.filter(is_active=True).order_by('order', 'id'),
            ),
            Prefetch(
                'drink_presets',
                queryset=DrinkOptionPreset.objects.order_by('order', 'id'),
            ),
            Prefetch(
                'items',
                queryset=MenuItem.objects.filter(is_available=True)
                .order_by('order', 'name')
                .prefetch_related(
                    Prefetch('sizes', queryset=MenuItemSize.objects.order_by('order', 'id')),
                ),
            ),
        )
    )


@cashier_required
def new_order(request):
    shift = Shift.objects.filter(cashier=request.user, status='open').first()
    if not shift:
        from django.contrib import messages
        messages.error(request, 'لازم تفتح شيفت الأول قبل ما تعمل طلب جديد.')
        return redirect('cashier_dashboard')
    categories = _cashier_menu_queryset()
    catalog = menu_catalog_payload(categories)
    tables = list(available_tables_qs(for_new_order=True).order_by('number'))
    waiters = Waiter.objects.filter(is_active=True)
    drivers = DeliveryDriver.objects.filter(is_active=True)
    return render(
        request,
        'pos/cashier/new_order.html',
        {
            'categories': categories,
            'menu_catalog': catalog,
            'tables': tables,
            'waiters': waiters,
            'drivers': drivers,
        },
    )


# ══════════════════════════════════════════════════════════════════════════
#  ORDER DETAIL
# ══════════════════════════════════════════════════════════════════════════

@cashier_required
def order_detail(request, order_id):
    order = get_object_or_404(
        prefetch_order_tables(
            Order.objects.select_related('waiter', 'driver')
            .prefetch_related(
                'items__menu_item__category',
                'items__selected_size',
            ),
        ),
        id=order_id,
        cashier=request.user,
    )
    categories = _cashier_menu_queryset()
    catalog = menu_catalog_payload(categories)
    profile = get_profile(request.user)
    all_tables = Table.objects.filter(is_active=True).order_by('number')
    selected_tids = {link.table_id for link in order.table_links.all()}
    busy = set()
    if order.status in ('open', 'printed') and order.order_type == 'dine_in':
        busy = busy_table_ids_global(exclude_order_id=order.id)
    drivers = DeliveryDriver.objects.filter(is_active=True).order_by('name')
    activities = order.activities.select_related('user').order_by('created_at')
    return render(
        request,
        'pos/cashier/order_detail.html',
        {
            'order': order,
            'categories': categories,
            'menu_catalog': catalog,
            'profile': profile,
            'tables_for_edit': all_tables,
            'table_edit_busy_ids': busy,
            'table_edit_selected_ids': selected_tids,
            'drivers': drivers,
            'activities': activities,
        },
    )


@cashier_required
def customer_invoice(request, order_id):
    order = get_object_or_404(
        prefetch_order_tables(
            Order.objects.select_related('waiter', 'driver')
            .prefetch_related('items__menu_item__category', 'items__selected_size'),
        ),
        id=order_id,
        cashier=request.user,
    )
    return render(request, 'pos/customer_invoice.html', {'order': order})


@cashier_required
def orders_list(request):
    shift = Shift.objects.filter(cashier=request.user, status='open').first()
    if shift:
        base_qs = Order.objects.filter(cashier=request.user, shift=shift)
    else:
        base_qs = Order.objects.none()
    orders = prefetch_order_tables(
        base_qs.select_related('waiter').order_by('-created_at')
    )
    order_stats = orders.aggregate(
        total=Count('id'),
        dine_in=Count('id', filter=Q(order_type='dine_in')),
        delivery=Count('id', filter=Q(order_type='delivery')),
    )
    status_stats = orders.aggregate(
        total=Count('id'),
        waiting=Count('id', filter=Q(status__in=['open', 'printed'])),
        completed=Count('id', filter=Q(status='completed')),
        cancelled=Count('id', filter=Q(status='cancelled')),
    )
    waiters = Waiter.objects.filter(is_active=True).order_by('name')
    profile = get_profile(request.user)
    return render(request, 'pos/cashier/orders_list.html', {
        'orders':       orders,
        'order_stats':  order_stats,
        'status_stats': status_stats,
        'waiters':      waiters,
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
        total = Decimal('0')
        for item_data in items_data:
            mi = get_object_or_404(MenuItem, id=int(item_data['id']))
            qty = int(item_data.get('quantity', 1))
            try:
                unit, meta = compute_order_item_unit_price(mi, item_data)
            except ValueError as err:
                return JsonResponse({'success': False, 'error': str(err)})
            sub = unit * qty
            total += sub
            note = (item_data.get('notes') or '')[:200]
            name_display = mi.name
            if meta.get('size_label'):
                name_display = f'{mi.name} ({meta["size_label"]})'
            line_parts = []
            if meta.get('drink_detail'):
                line_parts.append(meta['drink_detail'])
            for a in (meta.get('extras_json') or {}).get('addons', []):
                line_parts.append(f'+ {a.get("name", "")}')
            if note:
                line_parts.append(note)
            line_note = ' · '.join(line_parts)
            preview_items.append({
                'name': name_display,
                'qty': qty,
                'price': float(unit),
                'subtotal': float(sub),
                'cat_type': mi.category.category_type,
                'notes': line_note,
            })

        ot = data.get('order_type', 'dine_in')
        table_ids = parse_table_ids_payload(data)
        if ot == 'dine_in':
            ok, err = validate_table_ids_for_new_order(table_ids)
            if not ok:
                return JsonResponse({'success': False, 'error': err})
            table_label = preview_tables_label(table_ids)
        else:
            table_label = '—'

        return JsonResponse({
            'success':       True,
            'items':         preview_items,
            'total':         float(total.quantize(Decimal('0.01'))),
            'table':         table_label,
            'order_type':    data.get('order_type', 'dine_in'),
            'customer_name': data.get('customer_name', ''),
            'notes':         data.get('notes', ''),
            'time':          timezone.localtime(timezone.now()).strftime('%Y-%m-%d') + '  ' + _fmt12(timezone.now()),
            'cashier':       request.user.get_full_name() or request.user.username,
        })
    except Exception as e:
        log.error(f'preview_order: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
#  API — DELIVERY CUSTOMER (lookup by phone)
# ══════════════════════════════════════════════════════════════════════════

_MIN_PHONE_DIGITS = 9


@cashier_required
@require_GET
def delivery_customer_lookup(request):
    """بحث عن عميل ديليفري محفوظ بالهاتف؛ تطبيع الرقم ليتطابق مع الحفظ عند الطباعة."""
    raw = request.GET.get('phone', '')
    key = DeliveryCustomer.normalize_phone(raw)
    if not key or len(key) < _MIN_PHONE_DIGITS:
        return JsonResponse({'success': True, 'found': False, 'too_short': True})
    try:
        c = DeliveryCustomer.objects.get(phone_key=key)
        return JsonResponse({
            'success': True,
            'found': True,
            'name': c.name or '',
            'address': c.address or '',
        })
    except DeliveryCustomer.DoesNotExist:
        return JsonResponse({'success': True, 'found': False})


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

        table_ids = parse_table_ids_payload(data)
        if order_type == 'dine_in':
            ok, err = validate_table_ids_for_new_order(table_ids)
            if not ok:
                return JsonResponse({'success': False, 'error': err})

        current_shift = Shift.objects.filter(cashier=request.user, status='open').first()
        if not current_shift:
            return JsonResponse({'success': False, 'error': 'لازم تفتح شيفت الأول قبل ما تعمل طلب'})

        with transaction.atomic():
            last_num = (
                Order.objects
                .filter(shift=current_shift)
                .select_for_update()
                .order_by('-shift_order_number')
                .values_list('shift_order_number', flat=True)
                .first()
            ) or 0
            next_num = last_num + 1

            order = Order.objects.create(
                cashier=request.user,
                shift=current_shift,
                shift_order_number=next_num,
                order_type=order_type,
                status='open',
                notes=data.get('notes', ''),
                waiter_id=data.get('waiter_id') or None,
                driver_id=data.get('driver_id') or None,
                customer_name=data.get('customer_name', ''),
                customer_phone=data.get('customer_phone', ''),
                customer_address=data.get('customer_address', ''),
            )

            if order_type == 'dine_in':
                sync_order_tables(order, table_ids)

            for item_data in items_data:
                mi = get_object_or_404(MenuItem, id=int(item_data['id']))
                qty = int(item_data.get('quantity', 1))
                note = (item_data.get('notes') or '')[:200]
                try:
                    unit, meta = compute_order_item_unit_price(mi, item_data)
                except ValueError as err:
                    raise ValueError(str(err)) from err
                mk = merge_key_from_payload(mi, item_data, meta)
                existing = None
                for oi in order.items.all():
                    if merge_key_from_oi(oi) == mk:
                        existing = oi
                        break
                if existing:
                    existing.quantity += qty
                    existing.save()
                else:
                    oi = OrderItem(
                        order=order,
                        menu_item=mi,
                        quantity=qty,
                        price=unit,
                        notes=note,
                    )
                    apply_meta_to_order_item(oi, meta)
                    oi.save()

            if order_type == 'delivery':
                DeliveryCustomer.upsert(
                    data.get('customer_phone', ''),
                    data.get('customer_name', ''),
                    data.get('customer_address', ''),
                )

        items_summary = ', '.join(
            f'{oi.quantity}× {oi.menu_item.name}' for oi in order.items.select_related('menu_item').all()
        )
        _log_activity(order, 'created', f'طلب جديد: {items_summary}', request.user)

        print_ok = _send_to_printer(order, open_drawer=False)

        order.status     = 'printed'
        order.printed_at = timezone.now()
        order.save()

        _log_activity(order, 'printed', 'طباعة وإرسال للمطبخ/البار', request.user)

        return JsonResponse({'success': True, 'order_id': order.id, 'order_number': order.display_number, 'print_success': print_ok})
    except ValueError as err:
        return JsonResponse({'success': False, 'error': str(err)})
    except Exception as e:
        log.error(f'create_order: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def update_order_tables(request, order_id):
    """تعديل طاولات طلب داخلي (كاشير على طلبه، أو مدير على أي طلب)."""
    try:
        order = get_object_or_404(Order, id=order_id)
        if not request.user.is_staff and order.cashier_id != request.user.id:
            return JsonResponse({'success': False, 'error': 'غير مصرح'}, status=403)
        if order.status in ('completed', 'cancelled'):
            return JsonResponse({'success': False, 'error': 'لا يمكن تعديل طلب منتهٍ أو ملغى'})
        if order.order_type != 'dine_in':
            return JsonResponse({'success': False, 'error': 'تعديل الطاولة للطلب الداخلي فقط'})
        data = json.loads(request.body or '{}')
        ids = parse_table_ids_payload(data)
        ok, err = validate_table_ids_for_existing_order(order, ids)
        if not ok:
            return JsonResponse({'success': False, 'error': err})
        with transaction.atomic():
            sync_order_tables(order, ids)
        order.refresh_from_db()
        _log_activity(order, 'tables_changed', f'تعديل الطاولات: {order.tables_label()}', request.user)
        return JsonResponse({'success': True, 'tables_label': order.tables_label()})
    except Exception as e:
        log.error(f'update_order_tables: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def update_order_driver(request, order_id):
    """تعيين أو إزالة طيار الديليفري (كاشير على طلبه، أو مدير)."""
    try:
        order = get_object_or_404(Order, id=order_id)
        if not request.user.is_staff and order.cashier_id != request.user.id:
            return JsonResponse({'success': False, 'error': 'غير مصرح'}, status=403)
        if order.status in ('completed', 'cancelled'):
            return JsonResponse({'success': False, 'error': 'لا يمكن تعديل طلب منتهٍ أو ملغى'})
        if order.order_type != 'delivery':
            return JsonResponse({'success': False, 'error': 'تعيين الطيار لطلبات الديليفري فقط'})
        data = json.loads(request.body or '{}')
        raw = data.get('driver_id')
        driver_id = None
        if raw not in (None, ''):
            try:
                driver_id = int(raw)
            except (TypeError, ValueError):
                return JsonResponse({'success': False, 'error': 'معرّف الطيار غير صالح'})
        if driver_id:
            drv = DeliveryDriver.objects.filter(id=driver_id, is_active=True).first()
            if not drv:
                return JsonResponse({'success': False, 'error': 'الطيار غير متاح'})
            order.driver_id = driver_id
        else:
            order.driver_id = None
        order.save(update_fields=['driver_id'])
        order.refresh_from_db()
        label = str(order.driver) if order.driver else '— بدون طيار —'
        _log_activity(order, 'driver_changed', f'تعيين الطيار: {label}', request.user)
        return JsonResponse({'success': True, 'driver_label': label, 'driver_id': order.driver_id})
    except Exception as e:
        log.error(f'update_order_driver: {e}')
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
        mi = get_object_or_404(MenuItem, id=data['menu_item_id'])
        qty = int(data.get('quantity', 1))
        note = (data.get('notes') or '')[:200]
        payload = {
            'id': mi.id,
            'size_id': data.get('size_id'),
            'addon_ids': data.get('addon_ids') or [],
            'drink_preset_ids': data.get('drink_preset_ids') or [],
            'drink_custom': data.get('drink_custom') or '',
            'notes': note,
        }
        try:
            unit, meta = compute_order_item_unit_price(mi, payload)
        except ValueError as err:
            return JsonResponse({'success': False, 'error': str(err)})
        mk = merge_key_from_payload(mi, payload, meta)
        existing = None
        for oi in order.items.all():
            if merge_key_from_oi(oi) == mk:
                existing = oi
                break
        changed_items = []
        if existing:
            existing.quantity += qty
            existing.save()
            changed_items.append(
                SimpleNamespace(
                    menu_item=existing.menu_item,
                    quantity=qty,
                    price=existing.price,
                    size_label=existing.size_label,
                    drink_detail=existing.drink_detail,
                    extras_json=existing.extras_json,
                    notes=existing.notes,
                )
            )
        else:
            oi = OrderItem(
                order=order,
                menu_item=mi,
                quantity=qty,
                price=unit,
                notes=note,
            )
            apply_meta_to_order_item(oi, meta)
            oi.save()
            changed_items.append(oi)

        _log_activity(order, 'item_added', f'إضافة {qty}× {mi.name}', request.user)

        print_ok = None
        if order.status == 'printed':
            print_ok = _send_order_update_to_printer(
                order,
                changed_items,
                action_label='إضافة',
                print_main_full=True,
            )
        return JsonResponse({'success': True, 'total': float(order.total), 'print_success': print_ok})
    except Exception as e:
        log.error(f'add_item: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
#  API — ADD ITEMS BATCH (طباعة واحدة للمطبخ/البار)
# ══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def add_items_batch(request, order_id):
    """يضيف عدة أصناف دفعة واحدة؛ إن كان الطلب مُطبَعاً تُرسل ورقة إضافة واحدة."""
    try:
        order = get_object_or_404(Order, id=order_id)
        if order.status in ['completed', 'cancelled']:
            return JsonResponse({'success': False, 'error': 'لا يمكن التعديل على هذا الطلب'})

        data = json.loads(request.body or '{}')
        raw_items = data.get('items')
        if not raw_items or not isinstance(raw_items, list):
            return JsonResponse({'success': False, 'error': 'أرسل قائمة أصناف للإضافة'})

        delta_by_oi = {}

        with transaction.atomic():
            for entry in raw_items:
                mi = get_object_or_404(MenuItem, id=int(entry['menu_item_id']))
                qty = int(entry.get('quantity', 1))
                if qty < 1:
                    return JsonResponse({'success': False, 'error': 'الكمية غير صالحة'})
                note = (entry.get('notes') or '')[:200]
                payload = {
                    'id': mi.id,
                    'size_id': entry.get('size_id'),
                    'addon_ids': entry.get('addon_ids') or [],
                    'drink_preset_ids': entry.get('drink_preset_ids') or [],
                    'drink_custom': entry.get('drink_custom') or '',
                    'notes': note,
                }
                try:
                    unit, meta = compute_order_item_unit_price(mi, payload)
                except ValueError as err:
                    return JsonResponse({'success': False, 'error': str(err)})
                mk = merge_key_from_payload(mi, payload, meta)
                existing = None
                for oi in order.items.select_related('menu_item').all():
                    if merge_key_from_oi(oi) == mk:
                        existing = oi
                        break
                if existing:
                    existing.quantity += qty
                    existing.save()
                    delta_by_oi[existing.id] = delta_by_oi.get(existing.id, 0) + qty
                else:
                    oi = OrderItem(
                        order=order,
                        menu_item=mi,
                        quantity=qty,
                        price=unit,
                        notes=note,
                    )
                    apply_meta_to_order_item(oi, meta)
                    oi.save()
                    delta_by_oi[oi.id] = qty

        changed_items = []
        summary_parts = []
        for oi_id, dq in delta_by_oi.items():
            oi = OrderItem.objects.select_related('menu_item__category').get(pk=oi_id)
            changed_items.append(
                SimpleNamespace(
                    menu_item=oi.menu_item,
                    quantity=dq,
                    price=oi.price,
                    size_label=oi.size_label,
                    drink_detail=oi.drink_detail,
                    extras_json=oi.extras_json,
                    notes=oi.notes,
                )
            )
            summary_parts.append(f'{dq}× {oi.menu_item.name}')

        desc = 'دفعة إضافة: ' + '، '.join(summary_parts)
        _log_activity(order, 'item_added', desc[:500], request.user)

        print_ok = None
        if order.status == 'printed':
            print_ok = _send_order_update_to_printer(
                order,
                changed_items,
                action_label='إضافة',
                print_main_full=True,
            )
        out = {'success': True, 'total': float(order.total)}
        if print_ok is not None:
            out['print_success'] = print_ok
        return JsonResponse(out)
    except Exception as e:
        log.error(f'add_items_batch: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
#  API — UPDATE ITEM META (no deletion)
# ══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def update_item_meta(request, order_id):
    try:
        order = get_object_or_404(Order, id=order_id)
        if order.status in ['completed', 'cancelled']:
            return JsonResponse({'success': False, 'error': 'لا يمكن التعديل على هذا الطلب'})

        data = json.loads(request.body)
        oi = get_object_or_404(OrderItem.objects.select_related('menu_item'), id=data['order_item_id'], order=order)
        mi = oi.menu_item
        note = (data.get('notes') or '')[:200]
        payload = {
            'id': mi.id,
            'size_id': data.get('size_id'),
            'addon_ids': data.get('addon_ids') or [],
            'drink_preset_ids': data.get('drink_preset_ids') or [],
            'drink_custom': data.get('drink_custom') or '',
            'notes': note,
        }
        try:
            unit, meta = compute_order_item_unit_price(mi, payload)
        except ValueError as err:
            return JsonResponse({'success': False, 'error': str(err)})

        oi.price = unit
        oi.notes = note
        apply_meta_to_order_item(oi, meta)
        oi.save()

        _log_activity(order, 'item_modified', f'تعديل {mi.name}', request.user)

        print_ok = None
        if order.status == 'printed':
            print_ok = _send_order_update_to_printer(
                order,
                [oi],
                action_label='تعديل',
                print_main_full=False,
            )
        return JsonResponse({'success': True, 'total': float(order.total), 'print_success': print_ok})
    except Exception as e:
        log.error(f'update_item_meta: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
#  API — REMOVE ITEM (always requires admin confirm)
# ══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def remove_item(request, order_id):
    try:
        order = get_object_or_404(Order, id=order_id)
        if order.status in ('completed', 'cancelled'):
            return JsonResponse({'success': False, 'error': 'لا يمكن تعديل أو حذف أصناف من طلب مكتمل أو ملغى — استخدم «إلغاء الطلب» من الإجراءات'})
        data  = json.loads(request.body)
        item  = get_object_or_404(
            OrderItem.objects.select_related('menu_item__category'),
            id=data['item_id'], order=order,
        )

        remove_qty = int(data.get('qty', 1))

        will_remove_all = remove_qty >= item.quantity
        other_items_count = order.items.exclude(id=item.id).count()
        is_last_item = will_remove_all and other_items_count == 0

        if is_last_item and not data.get('cancellation_reason'):
            return JsonResponse({
                'success': False,
                'will_cancel_order': True,
                'error': 'هذا آخر صنف — سيتم إلغاء الطلب',
            })

        admin_user = authenticate(
            request,
            username=data.get('admin_username', ''),
            password=data.get('admin_password', '')
        )
        if not admin_user or not admin_user.is_staff:
            return JsonResponse({'success': False, 'error': 'يلزم تاكيد المدير', 'need_admin': True})

        if is_last_item:
            reason = (data.get('cancellation_reason') or '').strip()
            if len(reason) < 2:
                return JsonResponse({'success': False, 'error': 'اكتب سبب الإلغاء (نص واضح)'})

            had_gone_to_stations = order.printed_at is not None

            order.cancel_approved_by = admin_user
            order.cancellation_reason = reason[:2000]
            order.status = 'cancelled'
            order.cancelled_at = timezone.now()
            order.save()
            _log_activity(order, 'cancelled', f'إلغاء (حذف آخر صنف) بواسطة {admin_user.username}: {reason[:200]}', request.user)

            print_success = None
            if had_gone_to_stations:
                order_print = prefetch_order_tables(
                    Order.objects.select_related('waiter', 'driver', 'cashier')
                    .prefetch_related('items__menu_item__category')
                    .filter(pk=order.pk)
                ).first()
                if order_print:
                    print_success = _send_order_cancel_to_printer(
                        order_print, reason, cancel_label='إلغاء جميع الأصناف')

            out = {'success': True, 'order_cancelled': True}
            if print_success is not None:
                out['print_success'] = print_success
            return JsonResponse(out)

        had_gone_to_stations = order.printed_at is not None

        removed_info = {
            'name': order_item_display_name(item),
            'qty': min(remove_qty, item.quantity),
            'notes': order_item_print_notes(item, show_addon_prices=False),
            'cat_type': item.menu_item.category.category_type,
        }

        if will_remove_all:
            item.delete()
        else:
            item.quantity -= remove_qty
            item.save()

        _log_activity(order, 'item_removed', f'حذف {removed_info["qty"]}× {removed_info["name"]}', request.user)

        print_ok = None
        if had_gone_to_stations:
            remaining = list(
                order.items.select_related('menu_item__category').all()
            )
            print_ok = _send_item_removal_to_printer(order, [removed_info], remaining)

        out = {'success': True, 'total': float(order.total)}
        if print_ok is not None:
            out['print_success'] = print_ok
        return JsonResponse(out)
    except Exception as e:
        log.error(f'remove_item: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
#  API — REMOVE ITEMS BATCH (تأكيد مدير مرة واحدة + ورقة حذف واحدة)
# ══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def remove_items_batch(request, order_id):
    try:
        order = get_object_or_404(Order, id=order_id)
        if order.status in ['completed', 'cancelled']:
            return JsonResponse({'success': False, 'error': 'لا يمكن التعديل على هذا الطلب'})

        data = json.loads(request.body or '{}')
        raw = data.get('removals')
        if not raw or not isinstance(raw, list):
            return JsonResponse({'success': False, 'error': 'أرسل قائمة حذف'})

        merged = defaultdict(int)
        for r in raw:
            merged[int(r['item_id'])] += int(r.get('qty', 1))

        items_by_id = {
            oi.id: oi
            for oi in order.items.select_related('menu_item__category').all()
        }

        for iid, q in merged.items():
            if iid not in items_by_id:
                return JsonResponse({'success': False, 'error': 'صنف غير موجود في الطلب'})
            if q < 1:
                return JsonResponse({'success': False, 'error': 'كمية الحذف غير صالحة'})
            if q > items_by_id[iid].quantity:
                return JsonResponse({'success': False, 'error': 'كمية الحذف أكبر من الموجود في الطلب'})

        remaining_units = 0
        for oi in items_by_id.values():
            take = merged.get(oi.id, 0)
            remaining_units += oi.quantity - take

        will_empty_order = remaining_units <= 0

        if will_empty_order and not data.get('cancellation_reason'):
            return JsonResponse({
                'success': False,
                'will_cancel_order': True,
                'error': 'هذا يفرّغ الطلب — سيتم إلغاء الطلب',
            })

        admin_user = authenticate(
            request,
            username=data.get('admin_username', ''),
            password=data.get('admin_password', ''),
        )
        if not admin_user or not admin_user.is_staff:
            return JsonResponse({'success': False, 'error': 'يلزم تاكيد المدير', 'need_admin': True})

        if will_empty_order:
            reason = (data.get('cancellation_reason') or '').strip()
            if len(reason) < 2:
                return JsonResponse({'success': False, 'error': 'اكتب سبب الإلغاء (نص واضح)'})

            had_gone_to_stations = order.printed_at is not None

            order.cancel_approved_by = admin_user
            order.cancellation_reason = reason[:2000]
            order.status = 'cancelled'
            order.cancelled_at = timezone.now()
            order.save()
            _log_activity(
                order,
                'cancelled',
                f'إلغاء (دفعة حذف تفرّغ الطلب) بواسطة {admin_user.username}: {reason[:200]}',
                request.user,
            )

            print_success = None
            if had_gone_to_stations:
                order_print = prefetch_order_tables(
                    Order.objects.select_related('waiter', 'driver', 'cashier')
                    .prefetch_related('items__menu_item__category')
                    .filter(pk=order.pk)
                ).first()
                if order_print:
                    print_success = _send_order_cancel_to_printer(
                        order_print, reason, cancel_label='إلغاء جميع الأصناف')

            out = {'success': True, 'order_cancelled': True}
            if print_success is not None:
                out['print_success'] = print_success
            return JsonResponse(out)

        had_gone_to_stations = order.printed_at is not None
        removed_infos = []
        log_parts = []

        with transaction.atomic():
            for iid in sorted(merged.keys()):
                qty = merged[iid]
                item = OrderItem.objects.select_related('menu_item__category').get(pk=iid, order=order)
                removed_infos.append({
                    'name': order_item_display_name(item),
                    'qty': qty,
                    'notes': order_item_print_notes(item, show_addon_prices=False),
                    'cat_type': item.menu_item.category.category_type,
                })
                log_parts.append(f'{qty}× {removed_infos[-1]["name"]}')
                if qty >= item.quantity:
                    item.delete()
                else:
                    item.quantity -= qty
                    item.save()

        order.refresh_from_db()
        _log_activity(
            order,
            'item_removed',
            'دفعة حذف: ' + '، '.join(log_parts)[:500],
            request.user,
        )

        print_ok = None
        if had_gone_to_stations:
            remaining = list(
                order.items.select_related('menu_item__category').all()
            )
            print_ok = _send_item_removal_to_printer(order, removed_infos, remaining)

        out = {'success': True, 'total': float(order.total)}
        if print_ok is not None:
            out['print_success'] = print_ok
        return JsonResponse(out)
    except Exception as e:
        log.error(f'remove_items_batch: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
#  API — COMPLETE ORDER (opens drawer)
# ══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def complete_order(request, order_id):
    try:
        order = get_object_or_404(Order, id=order_id, cashier=request.user)
        if order.status == 'completed':
            return JsonResponse({'success': False, 'error': 'الطلب مكتمل بالفعل'})
        if order.status == 'cancelled':
            return JsonResponse({'success': False, 'error': 'لا يمكن إكمال طلب ملغي'})

        order.status = 'completed'
        order.completed_at = timezone.now()
        order.save(update_fields=['status', 'completed_at'])
        _log_activity(order, 'completed', 'تم إنهاء الطلب وفتح الدرج', request.user)
        drawer_ok = _open_drawer()
        return JsonResponse({'success': True, 'drawer_opened': drawer_ok})
    except Exception as e:
        log.error(f'complete_order: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def complete_orders_batch(request):
    """إكمال عدة طلبات دفعة واحدة من شاشة طلبات الشيفت."""
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        data = {}

    raw_ids = data.get('order_ids') or []
    if not isinstance(raw_ids, list):
        return JsonResponse({'success': False, 'error': 'صيغة الطلب غير صحيحة'})

    order_ids = []
    for raw in raw_ids:
        try:
            oid = int(raw)
        except (TypeError, ValueError):
            continue
        if oid not in order_ids:
            order_ids.append(oid)

    if not order_ids:
        return JsonResponse({'success': False, 'error': 'اختر طلبًا واحدًا على الأقل'})

    # حماية إضافية: حد أقصى في الطلب الواحد.
    if len(order_ids) > 120:
        return JsonResponse({'success': False, 'error': 'عدد كبير جدًا من الطلبات دفعة واحدة'})

    qs = Order.objects.filter(id__in=order_ids, cashier=request.user)
    by_id = {o.id: o for o in qs}

    completed_ids = []
    failed = []
    now = timezone.now()

    with transaction.atomic():
        for oid in order_ids:
            order = by_id.get(oid)
            if not order:
                failed.append({'id': oid, 'error': 'الطلب غير موجود أو غير مصرح'})
                continue
            if order.status == 'completed':
                failed.append({'id': oid, 'error': 'الطلب مكتمل بالفعل'})
                continue
            if order.status == 'cancelled':
                failed.append({'id': oid, 'error': 'لا يمكن إكمال طلب ملغي'})
                continue

            order.status = 'completed'
            order.completed_at = now
            order.save(update_fields=['status', 'completed_at'])
            _log_activity(order, 'completed', 'تم إنهاء الطلب (دفعة جماعية)', request.user)
            completed_ids.append(oid)

    # فتح الدرج مرة واحدة بعد إنهاء الدفعة كلها (وليس لكل طلب)
    drawer_opened = False
    if completed_ids:
        drawer_opened = bool(_open_drawer())

    return JsonResponse({
        'success': bool(completed_ids),
        'completed_ids': completed_ids,
        'completed_count': len(completed_ids),
        'failed': failed,
        'drawer_opened': drawer_opened,
    })


# ══════════════════════════════════════════════════════════════════════════
#  API — CANCEL ORDER (needs admin confirm if printed)
# ══════════════════════════════════════════════════════════════════════════

@login_required
@require_POST
def cancel_order(request, order_id):
    try:
        order = get_object_or_404(
            Order.objects.filter(cashier=request.user).prefetch_related(
                'items__menu_item__category',
            ),
            id=order_id,
        )

        # اقرأ الـ body بس لو في content
        data = {}
        if request.body:
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                data = {}

        if order.status == 'cancelled':
            return JsonResponse({'success': False, 'error': 'الطلب ملغي بالفعل'})

        if order.status not in ('open', 'printed', 'completed'):
            return JsonResponse({'success': False, 'error': 'لا يمكن إلغاء هذا الطلب في حالته الحالية'})

        was_completed = order.status == 'completed'

        reason = (data.get('cancellation_reason') or '').strip()
        if len(reason) < 2:
            return JsonResponse({'success': False, 'error': 'اكتب سبب الإلغاء (نص واضح)'})

        admin_user = authenticate(
            request,
            username=data.get('admin_username', ''),
            password=data.get('admin_password', ''),
        )
        if not admin_user or not admin_user.is_staff:
            return JsonResponse({'success': False, 'error': 'يلزم تاكيد المدير', 'need_admin': True})

        had_gone_to_stations = order.printed_at is not None

        order.cancel_approved_by = admin_user
        order.cancellation_reason = reason[:2000]

        order.status = 'cancelled'
        order.cancelled_at = timezone.now()
        order.save()

        if was_completed:
            _log_activity(
                order,
                'cancelled',
                f'إلغاء بعد إنهاء الطلب (تسجيل فقط — بدون إشعار مطبخ) بواسطة {admin_user.username}: {reason[:200]}',
                request.user,
            )
        else:
            _log_activity(
                order,
                'cancelled',
                f'إلغاء بواسطة {admin_user.username}: {reason[:200]}',
                request.user,
            )

        print_success = None
        # طلب مكتمل ثم إلغاء: لا نُرسل للمطبخ/البار (كان الطلب منتهياً أصلاً)
        if not was_completed and had_gone_to_stations:
            order_print = prefetch_order_tables(
                Order.objects.select_related('waiter', 'driver', 'cashier')
                .prefetch_related('items__menu_item__category')
                .filter(pk=order.pk)
            ).first()
            if order_print:
                print_success = _send_order_cancel_to_printer(
                    order_print,
                    order_print.cancellation_reason or '',
                )

        out = {'success': True}
        if was_completed:
            out['printer_skipped'] = True
        if print_success is not None:
            out['print_success'] = print_success
        return JsonResponse(out)
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
        ok = _reprint_main_only(order, open_drawer=data.get('open_drawer', False))
        _log_activity(order, 'reprinted', f'إعادة طباعة (الحالة: {order.get_status_display()})', request.user)
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


def _shift_orders_qs(cashier, shift, *, close_snapshot_at=None):
    """طلبات الشيفت (مطبوع + مكتمل) المرتبطة مباشرةً بالشيفت."""
    return prefetch_order_tables(
        shift_orders_qs(cashier, shift)
        .select_related('waiter', 'driver')
        .prefetch_related('items__menu_item__category')
    )


def _shift_incomplete_orders_count(cashier, shift):
    """مفتوح أو قيد الانتظار — يمنع إغلاق الشيفت حتى تُكمّل الطلبات."""
    return Order.objects.filter(
        shift=shift,
        status__in=['open', 'printed'],
    ).count()


def _shift_orders_total_sum(cashier, shift):
    """مجموع مبيعات الطلبات = نقد دخل الدرج (مطبوع + مكتمل منذ بداية الشيفت)."""
    return sum(Decimal(str(o.total)) for o in _shift_orders_qs(cashier, shift))


def _fmt_j(m) -> str:
    return f"{Decimal(str(m)).quantize(Decimal('0.01')):.2f}"


def _fmt_shift_diff(diff: Decimal) -> str:
    d = Decimal(str(diff)).quantize(Decimal('0.01'))
    if d > 0:
        return f'+{_fmt_j(d)}'
    if d < 0:
        return f'-{_fmt_j(abs(d))}'
    return _fmt_j(d)


def _build_shift_report_lines(
    shift,
    cashier_user,
    orders_list,
    inventory_entries,
    cash_input: Decimal,
    orders_total: Decimal,
    inventory_total: Decimal,
    sys_total: Decimal,
    diff: Decimal,
    cancelled_orders_count: int = 0,
):
    """سطور فاتورة تقرير إنهاء الشيفت للطابعة الرئيسية."""
    end = shift.end_time or timezone.now()
    end_local = timezone.localtime(end)
    start_local = timezone.localtime(shift.start_time)
    rep_date = end_local.strftime('%Y-%m-%d')
    rep_time = _fmt12_raw(end_local)
    cashier_name = cashier_user.get_full_name() or cashier_user.username

    def row(label, value, bold_val=False):
        return {
            'cols': [
                {'text': str(value), 'width': 0.42, 'align': 'left', 'bold': bold_val},
                {'text': label, 'width': 0.58, 'align': 'right', 'bold': True},
            ]
        }

    lines = [
        {'spacer': True, 'height': 6},
        {'text': 'تقارير اليوم — إنهاء الشيفت', 'align': 'center', 'bold': True, 'size': 'xlarge'},
        {'divider': True, 'divider_style': 'double'},
        {'text': f'تاريخ التقرير: {rep_date}   الوقت: {rep_time}', 'align': 'center', 'size': 'small'},
        {'text': f'الشيفت: من {_fmt12_raw(start_local)} {start_local.strftime("%Y-%m-%d")} إلى {_fmt12_raw(end_local)} {end_local.strftime("%Y-%m-%d")}', 'align': 'center', 'size': 'small'},
        {'divider': True, 'divider_style': 'double'},
    ]

    dine = [o for o in orders_list if o.order_type == 'dine_in']
    deliv = [o for o in orders_list if o.order_type == 'delivery']
    cnt_d, sum_d = len(dine), sum(Decimal(str(o.total)) for o in dine)
    cnt_v, sum_v = len(deliv), sum(Decimal(str(o.total)) for o in deliv)
    cnt_all, sum_all = cnt_d + cnt_v, sum_d + sum_v

    # —— تفاصيل الطلبات (جدول: داخلي / ديليفري) ——
    lines.append({'text': 'تفاصيل الطلبات', 'align': 'center', 'bold': True})
    lines.append({'divider': True, 'divider_style': 'dashed'})
    lines.append({
        'cols': [
            {'text': '', 'width': 0.26, 'align': 'right'},
            {'text': 'داخلي', 'width': 0.37, 'align': 'center', 'bold': True},
            {'text': 'ديليفري', 'width': 0.37, 'align': 'center', 'bold': True},
        ],
        'size': 'small',
        'bold': True,
    })
    lines.append({'divider': True, 'divider_style': 'dashed'})
    lines.append({
        'cols': [
            {'text': 'عدد الطلبات', 'width': 0.26, 'align': 'right', 'bold': True},
            {'text': str(cnt_d), 'width': 0.37, 'align': 'center'},
            {'text': str(cnt_v), 'width': 0.37, 'align': 'center'},
        ],
        'size': 'small',
    })
    lines.append({
        'cols': [
            {'text': 'السعر', 'width': 0.26, 'align': 'right', 'bold': True},
            {'text': f'{_fmt_j(sum_d)} ج', 'width': 0.37, 'align': 'center'},
            {'text': f'{_fmt_j(sum_v)} ج', 'width': 0.37, 'align': 'center'},
        ],
        'size': 'small',
    })
    lines.append({'divider': True, 'divider_style': 'dashed'})
    lines.append({
        'cols': [
            {'text': 'الإجمالي', 'width': 0.22, 'align': 'right', 'bold': True},
            {'text': f'إجمالي الأوردرات: {cnt_all}', 'width': 0.39, 'align': 'center', 'bold': True},
            {'text': f'إجمالي السعر: {_fmt_j(sum_all)} ج', 'width': 0.39, 'align': 'center', 'bold': True},
        ],
        'size': 'small',
        'bold': True,
    })
    lines.append({
        'text': '(مجموع داخلي + ديليفري)',
        'align': 'center',
        'size': 'small',
    })
    lines.append({'divider': True, 'divider_style': 'double'})

    # —— الويتر ——
    lines.append({'text': 'حسب الويتر', 'align': 'center', 'bold': True})
    lines.append({'divider': True, 'divider_style': 'dashed'})
    by_waiter = defaultdict(lambda: {'name': '', 'count': 0, 'total': Decimal(0)})
    no_waiter_dine_cnt = 0
    no_waiter_dine_sum = Decimal(0)
    for o in orders_list:
        tot = Decimal(str(o.total))
        if o.waiter_id:
            k = o.waiter_id
            by_waiter[k]['name'] = o.waiter.name
            by_waiter[k]['count'] += 1
            by_waiter[k]['total'] += tot
        elif o.order_type == 'dine_in':
            no_waiter_dine_cnt += 1
            no_waiter_dine_sum += tot
    if by_waiter:
        for wid in sorted(by_waiter.keys(), key=lambda x: by_waiter[x]['name']):
            w = by_waiter[wid]
            lines.append(row(w['name'], f"{w['count']} طلب · {_fmt_j(w['total'])} ج"))
    else:
        lines.append({'text': '(لا توجد طلبات مرتبطة بالويتر)', 'align': 'center', 'size': 'small'})
    if no_waiter_dine_cnt:
        lines.append(row('داخلي بدون ويتر', f'{no_waiter_dine_cnt} طلب · {_fmt_j(no_waiter_dine_sum)} ج'))
    lines.append({'divider': True, 'divider_style': 'double'})

    # —— مطبخ / بار / أخرى (بنود) ——
    kitchen_ids, bar_ids, other_ids = set(), set(), set()
    kitchen_rev = bar_rev = other_rev = Decimal(0)
    for o in orders_list:
        for it in o.items.all():
            ct = it.menu_item.category.category_type
            sub = Decimal(str(it.subtotal))
            if ct == 'food':
                kitchen_rev += sub
                kitchen_ids.add(o.id)
            elif ct == 'drink':
                bar_rev += sub
                bar_ids.add(o.id)
            else:
                other_rev += sub
                other_ids.add(o.id)

    lines.append({'text': 'المطبخ والبار (إيرادات حسب نوع الصنف)', 'align': 'center', 'bold': True})
    lines.append({'divider': True, 'divider_style': 'dashed'})
    lines.append(row('المطبخ — عدد الطلبات', str(len(kitchen_ids))))
    lines.append(row('المطبخ — إجمالي أصناف الأكل', f'{_fmt_j(kitchen_rev)} ج'))
    lines.append(row('البار — عدد الطلبات', str(len(bar_ids))))
    lines.append(row('البار — إجمالي أصناف المشروبات', f'{_fmt_j(bar_rev)} ج'))
    if other_ids:
        lines.append(row('أخرى — عدد الطلبات', str(len(other_ids))))
        lines.append(row('أخرى — الإجمالي', f'{_fmt_j(other_rev)} ج'))
    sum_kb = kitchen_rev + bar_rev + other_rev
    lines.append({'divider': True, 'divider_style': 'dashed'})
    lines.append(row('إجمالي بنود (مطبخ+بار+أخرى)', f'{_fmt_j(sum_kb)} ج', bold_val=True))
    lines.append({'text': '* طلب واحد قد يُحسب في المطبخ والبار معاً إن كان فيه أكل ومشروب', 'align': 'center', 'size': 'small'})
    lines.append({'divider': True, 'divider_style': 'double'})

    # —— واردات ——
    lines.append({'text': 'واردات الشيفت (مخزون)', 'align': 'center', 'bold': True})
    lines.append({'divider': True, 'divider_style': 'dashed'})
    if inventory_entries:
        for inv in inventory_entries:
            lines.append({
                'cols': [
                    {'text': f'{_fmt_j(inv.total_cost)} ج', 'width': 0.3, 'align': 'left'},
                    {'text': inv.name[:36] + ('…' if len(inv.name) > 36 else ''), 'width': 0.7, 'align': 'right'},
                ],
                'size': 'small',
            })
        lines.append(row('إجمالي الواردات', f'{_fmt_j(inventory_total)} ج', bold_val=True))
    else:
        lines.append({'text': 'لا توجد واردات مسجّلة', 'align': 'center', 'size': 'small'})
    lines.append({'divider': True, 'divider_style': 'double'})

    lines.append({'text': 'طلبات ملغاة', 'align': 'center', 'bold': True})
    lines.append({'divider': True, 'divider_style': 'dashed'})
    lines.append(row('عدد الطلبات الملغاة (لا تُحسب في المبيعات)', str(cancelled_orders_count)))
    lines.append({'text': 'تُسجَّل للمراجعة فقط — غير مضمّنة في مفروض المبيعات أو الإيراد أعلاه', 'align': 'center', 'size': 'small'})
    lines.append({'divider': True, 'divider_style': 'double'})

    # —— مطابقة الدرج ——
    lines.append({'text': 'مطابقة الدرج', 'align': 'center', 'bold': True})
    lines.append({'divider': True, 'divider_style': 'dashed'})
    lines.append(row('مفروض المبيعات (طلبات مطبوعة + مكتملة)', f'{_fmt_j(orders_total)} ج'))
    lines.append(row('واردات الشيفت (خرج من الدرج للمخزون)', f'{_fmt_j(inventory_total)} ج'))
    lines.append(row('مجموع المطابقة (مبيعات + واردات)', f'{_fmt_j(sys_total)} ج', bold_val=True))
    lines.append(row('الدرج بعد العدّ', f'{_fmt_j(cash_input)} ج', bold_val=True))
    lines.append(row('الفرق (زيادة / نقص)', f'{_fmt_shift_diff(diff)} ج', bold_val=True))
    lines.append({'text': 'موجب = زيادة · سالب = نقص', 'align': 'center', 'size': 'small'})
    rev_booked = revenue_booked_from_shift_close(orders_total, diff)
    lines.append({'divider': True, 'divider_style': 'dashed'})
    lines.append(row('إيراد مسجّل للتقارير (مبيعات + زيادة الدرج)', f'{_fmt_j(rev_booked)} ج', bold_val=True))
    lines.append({'text': 'عند العجز: يُحتسب المبيعات فقط — الزيادة تُضاف للإيراد عند وجودها', 'align': 'center', 'size': 'small'})
    lines.append({'divider': True, 'divider_style': 'double'})
    lines.append(row('الكاشير', cashier_name, bold_val=True))
    lines.append({'spacer': True, 'height': 6})
    lines.append({'text': 'نهاية التقرير — شكراً', 'align': 'center', 'bold': True, 'size': 'small'})
    lines.append({'spacer': True, 'height': 12})

    return lines


def _send_shift_report_to_printer(main_lines) -> bool:
    """يُرسل التقرير إلى MAIN_PRINTER فقط (لا مطبخ ولا بار)."""
    if not http_requests:
        return False
    try:
        payload = {
            'main_lines': main_lines,
            'kitchen_lines': [],
            'bar_lines': [],
            'open_drawer': False,
            'main_only': True,  # print_service يتجاهل أي مطبخ/بار حتى لو وُجدت
        }
        r = http_requests.post(settings.PRINT_SERVICE_URL, json=payload, timeout=12)
        if r.status_code == 200:
            return bool(r.json().get('success', False))
        return False
    except Exception as e:
        log.error(f'_send_shift_report_to_printer: {e}')
        return False


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
    pending_orders_count = 0
    cancelled_in_shift = 0
    if shift:
        orders_total = _shift_orders_total_sum(request.user, shift)
        inventory_out = _shift_inventory_total(shift)
        pending_orders_count = _shift_incomplete_orders_count(request.user, shift)
        cancelled_in_shift = shift_cancelled_orders_count(request.user, shift)
    return render(
        request,
        'pos/cashier/end_shift.html',
        {
            'shift': shift,
            'orders_total': orders_total,
            'inventory_out': inventory_out,
            'pending_orders_count': pending_orders_count,
            'cancelled_in_shift': cancelled_in_shift,
        },
    )


@cashier_required
@require_POST
def submit_shift_end(request):
    try:
        shift = Shift.objects.filter(cashier=request.user, status='open').first()
        if not shift:
            return JsonResponse({'success': False, 'error': 'مفيش شيفت مفتوح'})

        if _shift_incomplete_orders_count(request.user, shift):
            return JsonResponse({
                'success': False,
                'error': 'مش ممكن تنهي الشيفت: فيه طلبات قيد الانتظار أو مفتوحة. اكملها من الشاشة الرئيسية الأول.',
            })

        cash_input = Decimal(request.POST.get('cash_in_drawer', '0'))
        end_at = timezone.now()

        orders_list = list(_shift_orders_qs(request.user, shift, close_snapshot_at=end_at).order_by('id'))
        cancelled_count = shift_cancelled_orders_count(request.user, shift, close_snapshot_at=end_at)
        orders_total = sum(Decimal(str(o.total)) for o in orders_list)
        inventory_total = _shift_inventory_total(shift)
        inventory_rows = list(
            InventoryEntry.objects.filter(shift=shift).order_by('id')
        )
        # مطابقة الدرج: مجمع السيستم = طلبات + واردات الشيفت؛ الفرق = الدرج الفعلي − المجمع
        sys_total = orders_total + inventory_total
        diff = cash_input - sys_total
        rev_booked = revenue_booked_from_shift_close(orders_total, diff)

        shift.cash_in_drawer = cash_input
        shift.system_total = sys_total
        shift.difference = diff
        shift.orders_total_at_close = orders_total
        shift.revenue_booked = rev_booked
        shift.end_time = end_at
        shift.status = 'closed'
        shift.notes = request.POST.get('notes', '')
        shift.save()

        report_lines = _build_shift_report_lines(
            shift,
            request.user,
            orders_list,
            inventory_rows,
            cash_input,
            orders_total,
            inventory_total,
            sys_total,
            diff,
            cancelled_orders_count=cancelled_count,
        )
        print_success = _send_shift_report_to_printer(report_lines)
        if not print_success:
            log.warning('submit_shift_end: فاتورة تقرير الشيفت لم تُطبع (تحقق من print_service)')

        return JsonResponse({
            'success': True,
            'orders_total': float(orders_total),
            'inventory_out': float(inventory_total),
            'system_total': float(sys_total),
            'cash_input': float(cash_input),
            'difference': float(diff),
            'revenue_booked': float(rev_booked),
            'cancelled_orders_count': cancelled_count,
            'status': 'زيادة' if diff > 0 else ('نقص' if diff < 0 else 'متطابق'),
            'print_success': print_success,
            'logout_url': request.build_absolute_uri(reverse('logout')),
        })
    except Exception as e:
        log.error(f'submit_shift_end: {e}')
        return JsonResponse({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
#  PRINT HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _append_order_notes_for_station_ticket(lines, order):
    """ملاحظات الطلب كاملة (ليست ملاحظة صنف) على تذكرة المطبخ/البار."""
    order_note = (order.notes or '').strip()
    if not order_note:
        return
    if len(order_note) > 500:
        order_note = order_note[:497] + '…'
    lines.append({'divider': True, 'divider_style': 'dashed'})
    lines.append({
        'text': f'ملاحظة الطلب: {order_note}',
        'align': 'center',
        'bold': True,
        'size': 'small',
    })


def _build_main_lines(order, *, show_status=False):
    items      = order.items.select_related('menu_item__category').all()
    now_date   = timezone.localtime(order.created_at).strftime('%Y-%m-%d')
    now_time   = _fmt12(order.created_at)
    type_label = 'داخلي' if order.order_type == 'dine_in' else 'ديليفري'
    cashier_name = order.cashier.get_full_name() or order.cashier.username

    title = 'فاتورة بيع'
    if show_status:
        title = f'فاتورة بيع — {order.get_status_display()}'

    lines = [
        {'spacer': True, 'height': 5},
        {'text': title, 'align': 'center', 'bold': True, 'size': 'xlarge'},
        {'divider': True, 'divider_style': 'double'},
    ]

    def _info_row(label, value):
        return {'cols': [
            {'text': str(value), 'width': 0.45, 'align': 'right'},
            {'text': label, 'width': 0.55, 'align': 'right', 'bold': True},
        ]}

    lines.append(_info_row('طلب رقم', f'#{order.display_number}'))
    lines.append(_info_row('النوع', type_label))

    if order.order_type == 'dine_in':
        lines.append(_info_row('الطاولة', order.tables_label()))
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
        disp = order_item_display_name(item)
        lines.append({'cols': [
            {'text': f'{subtotal} ج', 'width': 0.25, 'align': 'left'},
            {'text': str(item.price), 'width': 0.2, 'align': 'center'},
            {'text': str(item.quantity), 'width': 0.15, 'align': 'center'},
            {'text': disp, 'width': 0.4, 'align': 'right'},
        ]})
        extra = order_item_print_notes(item)
        if extra:
            lines.append({'text': f'  * {extra}', 'align': 'right', 'size': 'small'})

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


def _build_section_lines_for_items(order, cat_type, items, action_label=''):
    items = [i for i in items if i.menu_item.category.category_type == cat_type]
    if not items:
        return []

    label = 'المطبخ' if cat_type == 'food' else 'البار'
    now_time = _fmt12(timezone.now()) if action_label else _fmt12(order.created_at)
    type_label = 'داخلي' if order.order_type == 'dine_in' else 'ديليفري'
    hdr = label if not action_label else f'{label} — {action_label}'

    lines = [
        {'spacer': True, 'height': 5},
        {'text': hdr, 'align': 'center', 'bold': True, 'size': 'xlarge'},
        {'divider': True, 'divider_style': 'double'},
        {'cols': [
            {'text': now_time, 'width': 0.3, 'align': 'left'},
            {'text': f'طلب #{order.display_number}', 'width': 0.4, 'align': 'center', 'bold': True},
            {'text': type_label, 'width': 0.3, 'align': 'right'},
        ], 'bold': True},
    ]
    if action_label:
        if action_label == 'إلغاء':
            lines.append({
                'text': 'تنبيه: طلب ملغى — لا تُنفَّذ الأصناف التالية',
                'align': 'center',
                'bold': True,
            })
        elif action_label == 'إلغاء جميع الأصناف':
            lines.append({
                'text': 'تنبيه: تم إلغاء جميع أصناف الطلب',
                'align': 'center',
                'bold': True,
            })
        else:
            lines.append({'text': f'تنبيه: {action_label} على طلب موجود', 'align': 'center', 'bold': True})
        lines.append({'divider': True, 'divider_style': 'dashed'})

    if order.order_type == 'dine_in':
        lines.append({'text': f'الطاولة: {order.tables_label()}', 'align': 'center', 'bold': True})
    elif order.order_type == 'delivery' and order.customer_name:
        lines.append({'text': f'العميل: {order.customer_name}', 'align': 'center', 'bold': True})

    _append_order_notes_for_station_ticket(lines, order)

    lines.append({'divider': True, 'divider_style': 'double'})

    for item in items:
        disp = order_item_display_name(item)
        lines.append({'cols': [
            {'text': str(item.quantity), 'width': 0.15, 'align': 'left', 'bold': True},
            {'text': disp, 'width': 0.85, 'align': 'right', 'bold': True},
        ], 'size': 'large', 'bold': True})
        extra = order_item_print_notes(item, show_addon_prices=False)
        if extra:
            lines.append({'text': f'  * {extra}', 'align': 'right', 'bold': True})
        lines.append({'divider': True, 'divider_style': 'dashed'})

    lines.append({'spacer': True, 'height': 10})
    return lines


def _build_section_lines(order, cat_type):
    items = [
        i for i in order.items.select_related('menu_item__category').all()
        if i.menu_item.category.category_type == cat_type
    ]
    return _build_section_lines_for_items(order, cat_type, items)


def _build_cancel_station_lines(order, cat_type, reason_note='', cancel_label='إلغاء'):
    """سطور مطبخ/بار لإشعار إلغاء الطلب (نفس أسلوب الإضافة/التعديل)."""
    items = [
        i for i in order.items.select_related('menu_item__category').all()
        if i.menu_item.category.category_type == cat_type
    ]
    if not items:
        return []
    lines = _build_section_lines_for_items(order, cat_type, items, action_label=cancel_label)
    note = (reason_note or '').strip()
    if note:
        lines.insert(-1, {
            'text': f'سبب الإلغاء: {note[:180]}' + ('…' if len(note) > 180 else ''),
            'align': 'center',
            'size': 'small',
        })
    return lines


def _send_order_cancel_to_printer(order, reason: str = '', cancel_label='إلغاء') -> bool:
    """يُبلّغ المطبخ/البار بإلغاء الطلب إن وُجدت أصناف تخص كل قسم."""
    if not http_requests:
        return False
    try:
        kitchen_lines = _build_cancel_station_lines(order, 'food', reason, cancel_label)
        bar_lines = _build_cancel_station_lines(order, 'drink', reason, cancel_label)
        if not kitchen_lines and not bar_lines:
            return True
        payload = {
            'main_lines': [],
            'kitchen_lines': kitchen_lines,
            'bar_lines': bar_lines,
            'open_drawer': False,
        }
        r = http_requests.post(settings.PRINT_SERVICE_URL, json=payload, timeout=6)
        if r.status_code == 200:
            return bool(r.json().get('success', False))
        return False
    except Exception as e:
        log.error(f'_send_order_cancel_to_printer: {e}')
        return False


def _build_remove_item_station_lines(order, cat_type, removed_infos, remaining_items):
    """سطور مطبخ/بار لإشعار حذف أصناف (واحد أو أكثر) مع عرض المتبقي للعمل."""
    relevant = [r for r in removed_infos if r['cat_type'] == cat_type]
    if not relevant:
        return []

    label = 'المطبخ' if cat_type == 'food' else 'البار'
    hdr = 'حذف أصناف' if len(relevant) > 1 else 'حذف صنف'
    alert = 'تنبيه: تم حذف أصناف من الطلب' if len(relevant) > 1 else 'تنبيه: تم حذف صنف من الطلب'
    now_time = _fmt12(timezone.now())
    type_label = 'داخلي' if order.order_type == 'dine_in' else 'ديليفري'

    lines = [
        {'spacer': True, 'height': 5},
        {'text': f'{label} — {hdr}', 'align': 'center', 'bold': True, 'size': 'xlarge'},
        {'divider': True, 'divider_style': 'double'},
        {'cols': [
            {'text': now_time, 'width': 0.3, 'align': 'left'},
            {'text': f'طلب #{order.display_number}', 'width': 0.4, 'align': 'center', 'bold': True},
            {'text': type_label, 'width': 0.3, 'align': 'right'},
        ], 'bold': True},
        {'text': alert, 'align': 'center', 'bold': True},
        {'divider': True, 'divider_style': 'dashed'},
    ]

    if order.order_type == 'dine_in':
        lines.append({'text': f'الطاولة: {order.tables_label()}', 'align': 'center', 'bold': True})
    elif order.order_type == 'delivery' and order.customer_name:
        lines.append({'text': f'العميل: {order.customer_name}', 'align': 'center', 'bold': True})

    _append_order_notes_for_station_ticket(lines, order)

    lines.append({'divider': True, 'divider_style': 'double'})

    lines.append({'text': '✖ تم الحذف:', 'align': 'right', 'bold': True, 'size': 'large'})
    lines.append({'divider': True, 'divider_style': 'dashed'})
    for removed_info in relevant:
        lines.append({'cols': [
            {'text': str(removed_info['qty']), 'width': 0.15, 'align': 'left', 'bold': True},
            {'text': removed_info['name'], 'width': 0.85, 'align': 'right', 'bold': True},
        ], 'size': 'large', 'bold': True})
        if removed_info.get('notes'):
            lines.append({'text': f'  * {removed_info["notes"]}', 'align': 'right', 'bold': True})
        lines.append({'divider': True, 'divider_style': 'dashed'})

    lines.append({'divider': True, 'divider_style': 'double'})

    remaining = [i for i in remaining_items if i.menu_item.category.category_type == cat_type]
    if remaining:
        lines.append({'text': '▶ المتبقي للعمل:', 'align': 'right', 'bold': True, 'size': 'large'})
        lines.append({'divider': True, 'divider_style': 'dashed'})
        for item in remaining:
            disp = order_item_display_name(item)
            lines.append({'cols': [
                {'text': str(item.quantity), 'width': 0.15, 'align': 'left', 'bold': True},
                {'text': disp, 'width': 0.85, 'align': 'right', 'bold': True},
            ], 'size': 'large', 'bold': True})
            extra = order_item_print_notes(item, show_addon_prices=False)
            if extra:
                lines.append({'text': f'  * {extra}', 'align': 'right', 'bold': True})
            lines.append({'divider': True, 'divider_style': 'dashed'})
    else:
        lines.append({'text': 'لا يوجد أصناف متبقية لهذا القسم', 'align': 'center', 'bold': True})

    lines.append({'spacer': True, 'height': 10})
    return lines


def _send_item_removal_to_printer(order, removed_infos, remaining_items) -> bool:
    """يُبلّغ المطبخ/البار بحذف أصناف من الطلب مع عرض المتبقي."""
    if not http_requests:
        return False
    try:
        kitchen_lines = _build_remove_item_station_lines(order, 'food', removed_infos, remaining_items)
        bar_lines = _build_remove_item_station_lines(order, 'drink', removed_infos, remaining_items)
        if not kitchen_lines and not bar_lines:
            return True
        payload = {
            'main_lines': [],
            'kitchen_lines': kitchen_lines,
            'bar_lines': bar_lines,
            'open_drawer': False,
        }
        r = http_requests.post(settings.PRINT_SERVICE_URL, json=payload, timeout=6)
        if r.status_code == 200:
            return bool(r.json().get('success', False))
        return False
    except Exception as e:
        log.error(f'_send_item_removal_to_printer: {e}')
        return False


def _send_order_update_to_printer(order, changed_items, action_label='إضافة', print_main_full=True) -> bool:
    if not http_requests:
        return False
    try:
        payload = {
            'main_lines': _build_main_lines(order) if print_main_full else [],
            'kitchen_lines': _build_section_lines_for_items(order, 'food', changed_items, action_label=action_label),
            'bar_lines': _build_section_lines_for_items(order, 'drink', changed_items, action_label=action_label),
            'open_drawer': False,
        }
        r = http_requests.post(settings.PRINT_SERVICE_URL, json=payload, timeout=6)
        if r.status_code == 200:
            return bool(r.json().get('success', False))
        return False
    except Exception as e:
        log.error(f'_send_order_update_to_printer: {e}')
        return False


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


def _reprint_main_only(order, open_drawer=False) -> bool:
    """إعادة طباعة فاتورة الأوردر على الطابعة الأساسية فقط (بدون مطبخ/بار) مع عرض حالة الطلب."""
    if not http_requests:
        return False
    try:
        payload = {
            'main_lines': _build_main_lines(order, show_status=True),
            'kitchen_lines': [],
            'bar_lines': [],
            'open_drawer': open_drawer,
        }
        r = http_requests.post(settings.PRINT_SERVICE_URL, json=payload, timeout=4)
        if r.status_code == 200:
            return bool(r.json().get('success', False))
        return False
    except Exception as e:
        log.error(f'_reprint_main_only: {e}')
        return False


def _open_drawer() -> bool:
    """يفتح الدرج مستقل عن الطباعة"""
    if not http_requests:
        log.error('مكتبة requests مش موجودة')
        return False

    try:
        url = getattr(settings, 'PRINT_SERVICE_URL', 'http://127.0.0.1:5050/print')
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