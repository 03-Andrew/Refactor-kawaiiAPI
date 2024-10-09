from rest_framework.response import Response

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .serializers import UserSerializer, UserProfileSerializer

from rest_framework import status
from rest_framework.authtoken.models import Token
from django.contrib.auth.models import User

from .models import UserProfile

from django.shortcuts import get_object_or_404

# Create your views here.
# @api_view(['POST'])
# def login(request):
#     userP = get_object_or_404(User, username = request.data['username'])
#     if not userP.check_password(request.data['password']):
#         return Response({"detail":'Not found'}, status=status.HTTP_404_NOT_FOUND)
#     token, created = Token.objects.get_or_create(user=userP)
#     serializer = UserSerializer(instance=userP)
#     return Response({"token":token.key, "user":serializer.data})


@api_view(['POST'])  # Ensure this view only accepts POST requests
def login(request):
    username = request.data.get('username')  # Use get() to avoid MultiValueDictKeyError
    password = request.data.get('password')
    
    # Check if username and password are provided
    if not username or not password:
        return Response({"detail": "Username and password are required."}, status=status.HTTP_400_BAD_REQUEST)

    # Attempt to retrieve the user
    userP = get_object_or_404(User, username=username)

    # Check the password
    if not userP.check_password(password):
        return Response({"detail": 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

    # Generate or retrieve the token
    token, created = Token.objects.get_or_create(user=userP)
    serializer = UserSerializer(instance=userP)

    # Return the token and user details
    return Response({"token": token.key, "user": serializer.data})

@api_view(['POST'])
def signup(request):
    serializer = UserSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        user = User.objects.get(username=request.data['username'])
        user.set_password(request.data['password'])
        user.save()
        token = Token.objects.create(user=user)
        return Response({"token":token.key, "user":serializer.data})
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def test_token(request):
    return Response("passed!")


@api_view(['GET'])
@authentication_classes([SessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_user(request):
    # Print the user to the console (for debugging purposes)
    print(f"Authenticated user: {request.user}")

    # Return the user's information as part of the response
    user_data = {
        "id": request.user.id,
        "username": request.user.username,
        "email": request.user.email,
        # You can include other user-related fields as needed
    }
    
    return Response(user_data)