from django.contrib import admin
from .models import UserProfile
# Register your models here.
class AllFieldsAdmin(admin.ModelAdmin):
    def get_list_display(self, request):
        # Get all field names dynamically
        fields = [field.name for field in self.model._meta.fields]
        # Ensure 'total_cost' is included if it exists
        return fields
    
    
admin.site.register(UserProfile, AllFieldsAdmin)