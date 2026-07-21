N+1

class GetAvailableRoomsNow(APIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]
    pagination_class = RoomPagination  # Set the pagination class

    def get(self, request):
        today = datetime.now().date()
        rooms = self.get_queryset()
        data ={}
        booking = Booking.objects.filter(check_in__lte=today, check_out__gte=today).first()
        for room in rooms:
        # Get the booking for today
            booking = Booking.objects.filter(room=room, check_in__lte=today, check_out__gte=today).first()
            if booking:  # If a booking exists for today
                data[room.id] = RoomSerializer(room).data # Store serialized data in response
                data[room.id]['is_booked'] = True
            else:
                data[room.id] = RoomSerializer(room).data  # No bookings for this room today
                data[room.id]['is_booked'] = False
            
        paginator = self.pagination_class()
        paginated_data = paginator.paginate_queryset(list(data.values()), request)  # Pass only values for pagination
        return paginator.get_paginated_response(paginated_data)
    
    def get_queryset(self):
        queryset = Room.objects.all() 
        room_type = self.request.GET.get('type')  
        sort = self.request.GET.get('sort')

        # Filtering 
        if room_type:
            queryset = queryset.filter(type__name=room_type)
                
        # Sorting
        if sort:
            if sort == 'ascroom':
                queryset = queryset.annotate(num_int=Cast('number', IntegerField())).order_by('num_int')
            elif sort == 'descroom':
                queryset = queryset.annotate(num_int=Cast('number', IntegerField())).order_by('-num_int')

        return queryset