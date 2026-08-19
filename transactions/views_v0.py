from django.db.models import Q
from rest_framework import generics
from drf_spectacular.utils import extend_schema, OpenApiParameter

from transactions.models import Billing, BillingStatus
from transactions.serializers import (
    BillingSerializer,
    BillingSerializerBase,
    BillingDetailSerializer,
)
from kawaiiAPI.permissions import IsReceptionistOrAdmin, AdminDeleteOnly


# ── V0 Unoptimized Views (without select_related / prefetch_related) ──────────

@extend_schema(tags=['Billing v0'])
class BillingListV0(generics.ListAPIView):
    serializer_class = BillingSerializer
    permission_classes = [IsReceptionistOrAdmin]

    @extend_schema(
        parameters=[
            OpenApiParameter('name', type=str),
            OpenApiParameter('status', type=str, enum=BillingStatus.values, many=True),
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        name = self.request.GET.get("name")
        statuses = self.request.GET.getlist("status")
        queryset = Billing.objects.all()

        if statuses:
            queryset = queryset.filter(Q(status__in=statuses)).distinct()
        if name:
            queryset = queryset.filter(
                Q(customer__first_name__icontains=name) |
                Q(customer__last_name__icontains=name)
            )

        return queryset


@extend_schema(tags=['Billing v0'])
class BillingSingleEntityV0(generics.RetrieveUpdateAPIView):
    queryset = Billing.objects.all()
    serializer_class = BillingSerializerBase
    permission_classes = [IsReceptionistOrAdmin]
    lookup_field = 'pk'


@extend_schema(tags=['Billing v0'])
class BillingDetailsV0(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [AdminDeleteOnly]
    serializer_class = BillingDetailSerializer
    queryset = Billing.objects.all()
    lookup_field = 'pk'
