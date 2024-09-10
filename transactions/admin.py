from django.contrib import admin
from .models import Transaction, Customer, FoodBill, Amenities, AmenitiesAvailed

class AllFieldsAdmin(admin.ModelAdmin):
    def get_list_display(self, request):
        # Get all field names dynamically
        fields = [field.name for field in self.model._meta.fields]
        # Ensure 'total_cost' is included if it exists
        if hasattr(self, 'get_total_cost_field'):
            fields.append('total_cost')
        return fields
    
    def get_readonly_fields(self, request, obj=None):
        # Optionally make fields read-only, e.g., 'total_cost'
        readonly_fields = super().get_readonly_fields(request)
        if hasattr(self, 'get_total_cost_field'):
            readonly_fields += ('total_cost',)
        return readonly_fields


class BookingAdmin(AllFieldsAdmin):
    def get_total_cost_field(self):
        # Ensure 'total_cost' is added dynamically
        return True

    def total_cost(self, obj):
        return obj.total_cost

    total_cost.short_description = 'Total Cost'

    

# Register your models here.
admin.site.register(Transaction, BookingAdmin)
admin.site.register(Customer, AllFieldsAdmin)
admin.site.register(FoodBill, AllFieldsAdmin)
admin.site.register(Amenities, AllFieldsAdmin)
admin.site.register(AmenitiesAvailed, AllFieldsAdmin)
