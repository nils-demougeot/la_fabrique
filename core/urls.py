from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('new_material/', views.new_material, name='new_material'),
]
