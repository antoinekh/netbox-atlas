"""
Removing a background image from storage when nothing refers to it any more.

Django leaves a stored file behind when its row goes, so without this every deleted layer, every
deleted floor and every replaced image grows the media directory for good.

Signals rather than an override of `FloorLayer.delete()`: a floor deleted with its layers
removes them by cascade, which never calls `delete()` on each one, while `post_delete` is sent
for every row a cascade removes. The file goes after the transaction commits, so a delete that
rolls back keeps its image.
"""

from django.db import transaction
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from netbox_atlas.models import FloorLayer


def _delete_when_unused(storage, name: str) -> None:
    """
    Delete one stored file after the commit, unless another layer still points at it.
    """

    def delete() -> None:
        if not FloorLayer.objects.filter(file=name).exists():
            storage.delete(name)

    transaction.on_commit(delete)


@receiver(post_delete, sender=FloorLayer)
def delete_layer_file(sender, instance: FloorLayer, **kwargs) -> None:
    if instance.file:
        _delete_when_unused(instance.file.storage, instance.file.name)


@receiver(pre_save, sender=FloorLayer)
def delete_replaced_layer_file(sender, instance: FloorLayer, **kwargs) -> None:
    if not instance.pk:
        return
    previous = FloorLayer.objects.filter(pk=instance.pk).values_list('file', flat=True).first()
    if previous and previous != instance.file.name:
        _delete_when_unused(instance.file.storage, previous)
