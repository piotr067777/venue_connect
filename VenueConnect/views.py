from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import ObjectDoesNotExist
from django.forms.models import model_to_dict
from django.shortcuts import redirect, get_object_or_404
from django.shortcuts import render
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import status
from rest_framework.views import APIView
from .forms import NameAuthForm, BookingForm
from .forms import NameAuthForm, SearchForm
from .forms import RegisterForm
from .models import User, Advertisement, BookingOrder, Venue
from .utils import email_verification_token, TimeRange


def home_view(request):
    return render(request, 'home.html')


def register(request):
    return render(request, 'register.html')


def not_found_view(request):
    return render(request, '404.html')


def verify_email_confirm(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, ObjectDoesNotExist):
        user = None
    if user is not None and email_verification_token.check_token(user, token):
        user.email_verified = True
        user.save()
        messages.success(request, 'Your email has been verified.')
        return redirect('/')

    messages.warning(request, 'The link is invalid.')
    return render(request, 'verify_email_confirm.html')


class RegisterView(APIView):
    form_class = RegisterForm

    @staticmethod
    def get(request, **kwargs):
        form = RegisterForm()
        return render(request, 'register.html', {'form': form}, **kwargs)

    @staticmethod
    def post(request):
        next = request.GET.get('next')
        form = RegisterForm(data=request.POST)
        if form.is_valid():
            user = form.save()
            request_scheme = 'https' if request.is_secure() else 'http'
            domain = get_current_site(request).domain
            if user is not None:
                # For testing other functionality of email verified user
                # Just assume that user is verified by email
                user.email_verified = True
                user.save()
                # user.send_verification_email(request_scheme, domain)
                login(request, user, backend='VenueConnect.backend.NameAuthenticationBackend')
                if next:
                    return redirect(next)
                return redirect('/')
        return render(request, 'register.html', {'form': form}, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    @staticmethod
    def get(request, **kwargs):
        if request.user.is_authenticated:
            return redirect(f'/users/{request.user.pk}')
        form = NameAuthForm()
        return render(request, 'login.html', {'form': form}, **kwargs)

    @staticmethod
    def post(request):
        form = NameAuthForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if user is not None and form.is_valid():
                login(request, user, backend='VenueConnect.backend.NameAuthenticationBackend')
                return redirect(f'/users/{user.pk}/', status.HTTP_200_OK)
            return redirect('/', status.HTTP_401_UNAUTHORIZED)
        return render(request, 'login.html', {'form': form}, status=status.HTTP_400_BAD_REQUEST)


class SearchView(APIView):
    @staticmethod
    def get(request, **kwargs):
        form = SearchForm()
        return render(request, 'search.html', {'form': form}, **kwargs)

    @staticmethod
    def post(request):
        form = SearchForm(data=request.POST)
        if form.is_valid():
            ads = Advertisement.filter(
                venue_type=form.cleaned_data['venue_type'],
                min_price=form.cleaned_data['min_price'],
                max_price=form.cleaned_data['max_price'],
                min_capacity=form.cleaned_data['min_capacity'],
                max_capacity=form.cleaned_data['max_capacity'],
                available_from=form.cleaned_data['available_from'],
                available_to=form.cleaned_data['available_to']
            )
            if ads:
                return render(request, 'advertisements.html', context={'advertisements': ads})
            return redirect('/404', status=status.HTTP_404_NOT_FOUND)
        return render(request, 'search.html', {'form': form})


def logout_view(request):
    if request.user.is_authenticated:
        logout(request)
        return redirect('/', status=status.HTTP_200_OK)
    return redirect('/', status=status.HTTP_401_UNAUTHORIZED)


class UsersView(APIView):
    @staticmethod
    def get(request, userid):
        try:
            user = User.objects.get(pk=userid)
            user = model_to_dict(user)
            return render(request, 'users.html', {'user': user})
        except ObjectDoesNotExist:
            return redirect('/404', status=status.HTTP_404_NOT_FOUND)


class AdvertisementsView(APIView):
    @staticmethod
    def get(request, userid):
        user = User.objects.get(pk=userid)
        advertisements = Advertisement.objects.filter(owner=user)
        if not advertisements:
            return redirect('/404', status=status.HTTP_404_NOT_FOUND)
        return render(request, 'advertisements.html', {'advertisements': advertisements})


class AdvertisementView(APIView):
    @staticmethod
    def get(request, userid, ad_id):
        try:
            ad = Advertisement.objects.filter(owner_id=userid).get(pk=ad_id)
            return render(request, 'advertisement.html', {'ad': ad})
        except ObjectDoesNotExist:
            return redirect('/404', status=status.HTTP_404_NOT_FOUND)


class BookingsView(APIView):
    @staticmethod
    def get(request, userid):
        bookings = BookingOrder.objects.filter(user_id=userid)
        if not bookings:
            return redirect('/404', status=status.HTTP_404_NOT_FOUND)
        return render(request, 'bookings.html', {'bookings': bookings})


class BookingView(APIView):
    @staticmethod
    def get(request, userid, booking_id):
        try:
            booking = BookingOrder.objects.filter(user_id=userid).get(pk=booking_id)
            return render(request, 'booking.html', {'booking': booking})
        except ObjectDoesNotExist:
            return redirect('/404', status=status.HTTP_404_NOT_FOUND)


class ProfileView(APIView):
    @staticmethod
    def get(request, userid):
        try:
            user = User.objects.get(pk=userid)
            return render(request, 'profile.html', {'user': user})
        except ObjectDoesNotExist:
            return redirect('/404', status=status.HTTP_404_NOT_FOUND)


class MakeBookingView(APIView):
    @staticmethod
    def get(request, userid, ad_id, venue_id):
        form = BookingForm()
        try:
            venue = Venue.objects.get(pk=venue_id)
            return render(request, 'make_booking.html', {
                'booking_form': form,
                'venue': venue
            })
        except ObjectDoesNotExist:
            return redirect('/404', status=status.HTTP_404_NOT_FOUND)

    @staticmethod
    def post(request, venue_id):
        form = BookingForm(request.POST)
        if form.is_valid():
            try:
                venue = Venue.objects.get(pk=venue_id)
                request.user.make_booking(venue, TimeRange(form.cleaned_data['start_time'],
                                                           form.cleaned_data['end_time']))
                return redirect('bookings', userid=request.user.id)
            except ObjectDoesNotExist:
                return redirect('/404', status=status.HTTP_404_NOT_FOUND)


