"""منطق مشترك لخيارات المنيو (أحجام، إضافات، تفاصيل مشروبات) وحساب سعر السطر."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Tuple

from .models import CategoryAddon, DrinkOptionPreset, MenuItem, MenuItemSize, OrderItem


def menu_catalog_payload(categories_qs):
    """بيانات JSON لشاشة الكاشير: تصنيفات + أصناف + أحجام + إضافات التصنيف + عناوين المشروب."""
    out = {'categories': []}
    for cat in categories_qs:
        c = {
            'id': cat.id,
            'name': cat.name,
            'category_type': cat.category_type,
            'enable_sizes': cat.enable_sizes,
            'enable_addons': cat.enable_addons,
            'enable_drink_options': cat.enable_drink_options,
            'addons': [
                {'id': a.id, 'name': a.name, 'price': float(a.price)}
                for a in cat.addons.filter(is_active=True).order_by('order', 'id')
            ],
            'drink_presets': [
                {'id': p.id, 'label': p.label}
                for p in cat.drink_presets.all().order_by('order', 'id')
            ],
            'items': [],
        }
        for it in cat.items.filter(is_available=True).order_by('order', 'name'):
            sizes = [
                {'id': s.id, 'name': s.name, 'price': float(s.price)}
                for s in it.sizes.all().order_by('order', 'id')
            ]
            base = float(it.price)
            min_p = min([s['price'] for s in sizes], default=base) if sizes else base
            c['items'].append({
                'id': it.id,
                'name': it.name,
                'price': base,
                'display_from': min_p,
                'sizes': sizes,
                'description': (it.description or '')[:300],
            })
        out['categories'].append(c)
    return out


def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal('0.01'))


def compute_order_item_unit_price(menu_item: MenuItem, item_data: dict) -> Tuple[Decimal, Dict[str, Any]]:
    """
    يحسب سعر الوحدة والبيانات الإضافية للحفظ.
    item_data: size_id (opt), addon_ids (list), drink_preset_ids (opt), drink_custom (str), notes (str)
    يرجع (unit_price, meta_dict للـ OrderItem: size_label, drink_detail, extras_json)
    """
    cat = menu_item.category
    size_id = item_data.get('size_id')
    addon_ids = item_data.get('addon_ids') or []
    if not isinstance(addon_ids, list):
        addon_ids = []

    base = _dec(menu_item.price)
    size_label = ''
    selected_size = None

    sizes_qs = menu_item.sizes.all().order_by('order', 'id')
    if cat.enable_sizes and sizes_qs.exists():
        if size_id:
            try:
                selected_size = MenuItemSize.objects.get(pk=int(size_id), menu_item=menu_item)
            except (MenuItemSize.DoesNotExist, TypeError, ValueError) as e:
                raise ValueError('حجم غير صالح لهذا الصنف') from e
            base = _dec(selected_size.price)
            size_label = selected_size.name
        else:
            selected_size = sizes_qs.first()
            base = _dec(selected_size.price)
            size_label = selected_size.name

    addon_total = Decimal('0')
    addons_meta = []
    if cat.enable_addons and addon_ids:
        valid = {
            a.id: a
            for a in CategoryAddon.objects.filter(
                category=cat, is_active=True, pk__in=[int(x) for x in addon_ids if str(x).isdigit()]
            )
        }
        for aid in addon_ids:
            try:
                pk = int(aid)
            except (TypeError, ValueError):
                continue
            a = valid.get(pk)
            if a:
                ap = _dec(a.price)
                addon_total += ap
                addons_meta.append({'id': a.id, 'name': a.name, 'price': str(ap)})

    unit_price = base + addon_total

    drink_parts = []
    if cat.enable_drink_options and cat.category_type == 'drink':
        preset_ids = item_data.get('drink_preset_ids') or []
        if isinstance(preset_ids, list) and preset_ids:
            plist = [
                p.label
                for p in DrinkOptionPreset.objects.filter(
                    category=cat, pk__in=[int(x) for x in preset_ids if str(x).isdigit()]
                ).order_by('order', 'id')
            ]
            drink_parts.extend(plist)
    dc = (item_data.get('drink_custom') or '').strip()
    if dc:
        drink_parts.append(dc)
    drink_detail = ' · '.join(drink_parts)

    meta = {
        'size_label': size_label,
        'drink_detail': drink_detail,
        'extras_json': {'addons': addons_meta},
        'selected_size': selected_size,
    }
    return unit_price, meta


def merge_key_from_payload(menu_item: MenuItem, item_data: dict, meta: dict) -> tuple:
    aids = []
    for x in item_data.get('addon_ids') or []:
        try:
            aids.append(int(x))
        except (TypeError, ValueError):
            pass
    aids.sort()
    sz = meta.get('selected_size')
    sz_id = sz.id if sz else 0
    return (
        menu_item.id,
        sz_id,
        tuple(aids),
        (meta.get('drink_detail') or '').strip(),
        (item_data.get('notes') or '').strip(),
    )


def merge_key_from_oi(oi: OrderItem) -> tuple:
    ex = oi.extras_json or {}
    aids = sorted(a.get('id') for a in ex.get('addons', []) if a.get('id') is not None)
    sz_id = oi.selected_size_id or 0
    return (
        oi.menu_item_id,
        sz_id,
        tuple(aids),
        (oi.drink_detail or '').strip(),
        (oi.notes or '').strip(),
    )


def apply_meta_to_order_item(oi: OrderItem, meta: dict):
    oi.size_label = meta.get('size_label') or ''
    oi.drink_detail = meta.get('drink_detail') or ''
    oi.extras_json = meta.get('extras_json') or {}
    sz = meta.get('selected_size')
    oi.selected_size = sz if sz else None


def order_item_display_name(oi: OrderItem) -> str:
    n = oi.menu_item.name
    if oi.size_label:
        n = f'{n} ({oi.size_label})'
    return n


def order_item_print_notes(oi: OrderItem) -> str:
    parts = []
    if oi.drink_detail:
        parts.append(oi.drink_detail)
    ex = oi.extras_json or {}
    for a in ex.get('addons', []):
        parts.append(f'+ {a.get("name", "")} ({a.get("price", "0")} ج)')
    if oi.notes:
        parts.append(oi.notes)
    return ' · '.join(p for p in parts if p)

