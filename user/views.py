from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()
from django.contrib.auth import authenticate

from rest_framework.response import Response
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from drf_spectacular.utils import extend_schema

from .serializers import UserSerializer, UserAuthSerializer, UserLoginSerializer


@extend_schema(
    tags=['Users'],
    description='Login with username and password. Returns JWT access and refresh tokens.',
    request=UserLoginSerializer,
    responses={200: {'description': 'JWT tokens + user data'}}
)
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def login(request):
    username = request.data.get('username')  # Use get() to avoid MultiValueDictKeyError
    password = request.data.get('password')
    
    # Check if username and password are provided
    if not username or not password:
        return Response({"detail": "Username and password are required."}, status=status.HTTP_400_BAD_REQUEST)

    # Attempt to retrieve the user
    userP = authenticate(request, username=username, password=password)

    # Check the password
    if userP is None:
        return Response({"detail": "Invalid credentials."},
                        status=status.HTTP_401_UNAUTHORIZED)
    
    # Generate or retrieve the token
    refresh = RefreshToken.for_user(userP)
    access_token = str(refresh.access_token)
    refresh_token = str(refresh)
    serializer = UserSerializer(instance=userP)

    # Return the token and user details
    return Response({"access": access_token, "refresh": refresh_token, "user": serializer.data})

@extend_schema(
    tags=['Users'],
    description='Register a new user account. Returns JWT access and refresh tokens.',
    request=UserAuthSerializer,
    responses={201: {'description': 'JWT tokens + user data'}},
)
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def signup(request):
    if 'email' not in request.data or 'username' not in request.data or 'password' not in request.data:
        return Response({"detail": "Email, username, and password are required."}, status=status.HTTP_400_BAD_REQUEST)
    user = User.objects.create_user(
        username=request.data['username'],
        password=request.data['password'],
        email=request.data['email'],
    )
    refresh = RefreshToken.for_user(user)
    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": UserSerializer(instance=user).data,
    })

@extend_schema(
    tags=['Users'],
    description='Verify JWT token is valid. Returns "passed!" if authenticated.',
)
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def test_token(request):
    return Response("passed!")


@extend_schema(
    tags=['Users'],
    description='Get current authenticated user info from JWT token.',
)
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def get_user(request):
    serializer = UserSerializer(instance=request.user)
    return Response(serializer.data)