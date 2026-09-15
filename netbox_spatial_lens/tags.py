"""
The tags in use on a drawing, for the Tags finder.

A drawing offers only the tags its own racks or devices carry, each with how many carry it, so
the list is short and every row narrows the drawing to something.
"""

from collections.abc import Iterable
from dataclasses import dataclass

__all__ = (
    'TagCount',
    'tags_in_use',
)


@dataclass
class TagCount:
    tag: object
    count: int


def tags_in_use(objects: Iterable) -> list[TagCount]:
    """
    Every tag on `objects`, with how many of them carry it, in name order.

    Reads `obj.tags.all()`, so the caller prefetches the tags or this costs a query per object.
    """
    counts: dict[int, TagCount] = {}
    for obj in objects:
        for tag in obj.tags.all():
            if tag.pk in counts:
                counts[tag.pk].count += 1
            else:
                counts[tag.pk] = TagCount(tag=tag, count=1)
    return sorted(counts.values(), key=lambda item: item.tag.name.lower())
