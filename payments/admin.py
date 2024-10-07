from django.contrib import admin
from .models import PaymentMethod, Payment, PaymentFor, PaymentStatus


class AllFieldsAdmin(admin.ModelAdmin):
    def get_list_display(self, request):
        # Get all field names dynamically
        fields = [field.name for field in self.model._meta.fields]
# Register your models here.


admin.site.register(Payment, AllFieldsAdmin)
admin.site.register(PaymentMethod, AllFieldsAdmin)
admin.site.register(PaymentFor, AllFieldsAdmin)
admin.site.register(PaymentStatus, AllFieldsAdmin)
