from django.contrib import admin
from .models import Room, RoomStatus, RoomType, Inclusions, Booking, BookingStatus

class AllFieldsAdmin(admin.ModelAdmin):
    def get_list_display(self, request):
        # Get all field names dynamically
        fields = [field.name for field in self.model._meta.fields]
        # Ensure 'total_cost' is included if it exists
        return fields
    
    def get_readonly_fields(self, request, obj=None):
        # Optionally make fields read-only, e.g., 'total_cost'
        readonly_fields = super().get_readonly_fields(request)
        if hasattr(self, 'get_number_of_nights_field'):
            readonly_fields += ('number_of_nights',)
        
        if hasattr(self, 'get_total_cost_field'):
            readonly_fields += ('total_cost',)
        

        return readonly_fields

class BookingAdmin(AllFieldsAdmin):
    def get_total_cost_field(self):
        # Ensure 'total_cost' is added dynamically
        return True
    def get_number_of_nights_field(self):
        # Ensure 'total_cost' is added dynamically
        return True
    
    def total_cost(self, obj):
        return obj.total_cost

    total_cost.short_description = 'Total Cost'

# Register your models here with the custom admin class
admin.site.register(Room, AllFieldsAdmin)
admin.site.register(RoomStatus, AllFieldsAdmin)
admin.site.register(RoomType, AllFieldsAdmin)
admin.site.register(Inclusions, AllFieldsAdmin)
admin.site.register(BookingStatus, AllFieldsAdmin)
admin.site.register(Booking, BookingAdmin)




# admin.site.register(Amenities, AllFieldsAdmin)
# admin.site.register(AmenitiesType, AllFieldsAdmin)