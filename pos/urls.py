from django.urls import path
from . import views, admin_views, cashier_views

urlpatterns = [

    # ── Auth ──────────────────────────────────────────────────────────────
    path('login/',  views.login_view,  name='login'),
    path('logout/', views.logout_view, name='logout'),

    # ── Router (dispatches by role) ───────────────────────────────────────
    path('', views.home, name='home'),

    # ══════════════════════════════════════════════════════════════════════
    #  ADMIN PANEL
    # ══════════════════════════════════════════════════════════════════════
    path('admin-panel/',                     admin_views.dashboard,           name='admin_dashboard'),

    # Menu
    path('admin-panel/menu/',                admin_views.menu_list,           name='admin_menu'),
    path('admin-panel/menu/category/add/',   admin_views.category_add,        name='admin_cat_add'),
    path('admin-panel/menu/category/<int:pk>/edit/',   admin_views.category_edit,  name='admin_cat_edit'),
    path('admin-panel/menu/category/<int:pk>/delete/', admin_views.category_delete,name='admin_cat_delete'),
    path('admin-panel/menu/item/add/',       admin_views.item_add,            name='admin_item_add'),
    path('admin-panel/menu/item/<int:pk>/edit/',   admin_views.item_edit,     name='admin_item_edit'),
    path('admin-panel/menu/item/<int:pk>/delete/', admin_views.item_delete,   name='admin_item_delete'),

    # Cashiers
    path('admin-panel/cashiers/',            admin_views.cashier_list,        name='admin_cashiers'),
    path('admin-panel/cashiers/add/',        admin_views.cashier_add,         name='admin_cashier_add'),
    path('admin-panel/cashiers/<int:pk>/edit/',   admin_views.cashier_edit,   name='admin_cashier_edit'),
    path('admin-panel/cashiers/<int:pk>/delete/', admin_views.cashier_delete, name='admin_cashier_delete'),

    # Tables
    path('admin-panel/tables/',              admin_views.tables_list,         name='admin_tables'),
    path('admin-panel/tables/add/',          admin_views.table_add,           name='admin_table_add'),
    path('admin-panel/tables/<int:pk>/edit/',   admin_views.table_edit,       name='admin_table_edit'),
    path('admin-panel/tables/<int:pk>/delete/', admin_views.table_delete,     name='admin_table_delete'),

    # Waiters
    path('admin-panel/waiters/',             admin_views.waiter_list,         name='admin_waiters'),
    path('admin-panel/waiters/add/',         admin_views.waiter_add,          name='admin_waiter_add'),
    path('admin-panel/waiters/<int:pk>/edit/',   admin_views.waiter_edit,     name='admin_waiter_edit'),
    path('admin-panel/waiters/<int:pk>/delete/', admin_views.waiter_delete,   name='admin_waiter_delete'),

    # Delivery
    path('admin-panel/delivery/',            admin_views.driver_list,         name='admin_drivers'),
    path('admin-panel/delivery/add/',        admin_views.driver_add,          name='admin_driver_add'),
    path('admin-panel/delivery/<int:pk>/edit/',   admin_views.driver_edit,    name='admin_driver_edit'),
    path('admin-panel/delivery/<int:pk>/delete/', admin_views.driver_delete,  name='admin_driver_delete'),

    # Inventory
    path('admin-panel/inventory/',           admin_views.inventory_list,      name='admin_inventory'),
    path('admin-panel/inventory/add/',       admin_views.inventory_add,       name='admin_inventory_add'),
    path('admin-panel/inventory/<int:pk>/delete/', admin_views.inventory_delete, name='admin_inventory_delete'),

    # Reports / Profits
    path('admin-panel/reports/',             admin_views.reports,             name='admin_reports'),

    # History
    path('admin-panel/history/',             admin_views.history,             name='admin_history'),
    path('admin-panel/history/<int:order_id>/', admin_views.order_history_detail, name='admin_order_detail'),
    path('admin-panel/history/<int:order_id>/invoice/', admin_views.admin_customer_invoice, name='admin_customer_invoice'),

    # Shifts
    path('admin-panel/shifts/',              admin_views.shifts_list,         name='admin_shifts'),
    path('admin-panel/shifts/<int:shift_id>/', admin_views.shift_detail,      name='admin_shift_detail'),

    # API — Admin approve
    path('api/admin-verify/',                views.admin_verify,              name='admin_verify'),

    # ══════════════════════════════════════════════════════════════════════
    #  CASHIER PANEL
    # ══════════════════════════════════════════════════════════════════════
    path('cashier/',                         cashier_views.dashboard,         name='cashier_dashboard'),
    path('cashier/order/new/',               cashier_views.new_order,         name='cashier_new_order'),
    path('cashier/order/<int:order_id>/',    cashier_views.order_detail,      name='cashier_order_detail'),
    path('cashier/order/<int:order_id>/invoice/', cashier_views.customer_invoice, name='cashier_customer_invoice'),
    path('cashier/orders/',                  cashier_views.orders_list,       name='cashier_orders'),
    path('cashier/inventory/',               cashier_views.cashier_inventory, name='cashier_inventory'),
    path('cashier/inventory/submit/',         cashier_views.cashier_inventory_submit, name='cashier_inventory_submit'),

    # API
    path('api/delivery/customer/',          cashier_views.delivery_customer_lookup, name='api_delivery_customer'),
    path('api/order/preview/',              cashier_views.preview_order,     name='api_preview'),
    path('api/order/create/',               cashier_views.create_order,      name='api_create_order'),
    path('api/order/<int:order_id>/add-item/',   cashier_views.add_item,     name='api_add_item'),
    path('api/order/<int:order_id>/add-items-batch/', cashier_views.add_items_batch, name='api_add_items_batch'),
    path('api/order/<int:order_id>/update-item/', cashier_views.update_item_meta, name='api_update_item'),
    path('api/order/<int:order_id>/remove-item/', cashier_views.remove_item, name='api_remove_item'),
    path('api/order/<int:order_id>/remove-items-batch/', cashier_views.remove_items_batch, name='api_remove_items_batch'),
    path('api/order/<int:order_id>/complete/',    cashier_views.complete_order, name='api_complete'),
    path('api/orders/complete-batch/',            cashier_views.complete_orders_batch, name='api_complete_batch'),
    path('api/order/<int:order_id>/cancel/',      cashier_views.cancel_order,   name='api_cancel'),
    path('api/order/<int:order_id>/reprint/',     cashier_views.reprint_order,  name='api_reprint'),
    path('api/order/<int:order_id>/tables/',      cashier_views.update_order_tables, name='api_order_tables'),
    path('api/order/<int:order_id>/driver/',      cashier_views.update_order_driver, name='api_order_driver'),
    path('api/drawer/open/',                cashier_views.open_drawer,       name='api_drawer'),
    path('cashier/shift/end/',              cashier_views.end_shift,         name='cashier_end_shift'),
    path('cashier/shift/end/submit/',       cashier_views.submit_shift_end,  name='cashier_submit_shift'),
]
