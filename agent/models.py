from django.db import models

# Create your models here.
class ChatMessages(models.Model):
    thread_id = models.CharField(max_length=255)
    human_message = models.TextField()
    ai_message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)