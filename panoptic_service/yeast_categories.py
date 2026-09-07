"""Class scheme the fine-tuned yeast panoptic model outputs. Kept in sync
with `backend/app/services/segmentation/yeast_categories.py`."""

YEAST_CATEGORIES = [
    {"id": 0, "name": "background"},
    {"id": 1, "name": "cell"},
    {"id": 2, "name": "shmoo"},
    {"id": 3, "name": "zygote"},
    {"id": 4, "name": "tetrad"},
    {"id": 5, "name": "lysis"},
    {"id": 6, "name": "spore"},
    {"id": 7, "name": "unknown"},
    {"id": 8, "name": "unknown"},
    {"id": 9, "name": "unknown"},
]


def class_name(class_id: int) -> str:
    if 0 <= class_id < len(YEAST_CATEGORIES):
        return YEAST_CATEGORIES[class_id]["name"]
    return "unknown"
