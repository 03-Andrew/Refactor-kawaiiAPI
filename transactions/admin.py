from django.contrib import admin
from .models import Billing, Customer, FoodBill, Amenities, AmenitiesAvailed, AdditonalPayment, GuestList, GuestStatus, Activity, ActivitiesAvailed, PaymentMethod, Payment, PaymentFor, PaymentStatus, BillingStatus

class AllFieldsAdmin(admin.ModelAdmin):
    def get_list_display(self, request):
        # Get all field names dynamically
        fields = [field.name for field in self.model._meta.fields]
        # Ensure 'total_cost', 'paid_amount', 'running_balance', and 'guest_list' are included if they exist
        if hasattr(self, 'get_total_cost_field'):
            fields.append('total_cost')
        if hasattr(self, 'get_paid_amount'):
            fields.append('paid_amount')
        if hasattr(self, 'get_running_balance'):
            fields.append('running_balance')
        if hasattr(self, 'get_guest_list_field'):
            fields.append('guest_list')
        return fields

    def get_readonly_fields(self, request, obj=None):
        # Optionally make fields read-only
        readonly_fields = super().get_readonly_fields(request, obj)
        if hasattr(self, 'get_total_cost_field'):
            readonly_fields = (*readonly_fields, 'total_cost')
        if hasattr(self, 'get_paid_amount'):
            readonly_fields = (*readonly_fields, 'paid_amount')
        if hasattr(self, 'get_running_balance'):
            readonly_fields = (*readonly_fields, 'running_balance')
        if hasattr(self, 'get_guest_list_field'):
            readonly_fields = (*readonly_fields, 'guest_list')
        return readonly_fields

class BookingAdmin(AllFieldsAdmin):
    def get_total_cost_field(self):
        return True

    def total_cost(self, obj):
        return obj.total_cost

    total_cost.short_description = 'Total Cost'
    
    def get_paid_amount(self):
        return True

    def paid_amount(self, obj):
        return obj.paid_amount

    paid_amount.short_description = 'Paid Amount'
    
    def get_running_balance(self):
        return True

    def running_balance(self, obj):
        return obj.running_balance

    running_balance.short_description = 'Running Balance'
    
    def get_guest_list_field(self):
        return True

    def guest_list(self, obj):
        return ', '.join(obj.guests)

    guest_list.short_description = 'Guests'

    

    

# Register your models here.
admin.site.register(Billing, BookingAdmin)
admin.site.register(BillingStatus, AllFieldsAdmin)
admin.site.register(Customer, AllFieldsAdmin)
admin.site.register(FoodBill, AllFieldsAdmin)
admin.site.register(Amenities, AllFieldsAdmin)
admin.site.register(AmenitiesAvailed, AllFieldsAdmin)
admin.site.register(GuestList, AllFieldsAdmin)
admin.site.register(GuestStatus, AllFieldsAdmin)
admin.site.register(Activity, AllFieldsAdmin)
admin.site.register(ActivitiesAvailed, AllFieldsAdmin)
admin.site.register(PaymentMethod, AllFieldsAdmin)
admin.site.register(PaymentFor, AllFieldsAdmin)
admin.site.register(PaymentStatus, AllFieldsAdmin)
admin.site.register(Payment, AllFieldsAdmin)
admin.site.register(AdditonalPayment, AllFieldsAdmin)