from drf_spectacular.openapi import AutoSchema


class AppTagAutoSchema(AutoSchema):
    APP_TAG_MAP = {
        'bookings': 'Bookings',
        'transactions': 'Transactions',
        'receptionist': 'Receptionist',
        'user': 'Users',
        'paymongo': 'PayMongo',
        'reports': 'Reports',
    }

    def get_tags(self):
        if hasattr(self.view, '_spectacular_annotation'):
            tags = getattr(self.view._spectacular_annotation, 'tags', None)
            if tags:
                return tags
        module = self.view.__module__
        for app_key, tag in self.APP_TAG_MAP.items():
            if app_key in module:
                return [tag]
        return []
