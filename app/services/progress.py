from sqlalchemy import func, select

from app.models.progress import Achievement, SortingEvent, UserAchievement
from app.schemas.progress import TreeResponse, UserAchievementResponse

STAGES = [
    (0, "seed", "Семя"),
    (1, "sprout", "Росток"),
    (3, "sapling", "Саженец"),
    (6, "young_tree", "Молодое дерево"),
    (11, "mature_tree", "Взрослое дерево"),
]


def metrics(db, user_id: int) -> tuple[int, int]:
    return db.execute(select(func.count(SortingEvent.id), func.count(func.distinct(SortingEvent.material_code)))
                      .where(SortingEvent.user_id == user_id)).one()


def tree(db, user_id: int) -> TreeResponse:
    count, distinct = metrics(db, user_id)
    unlocked = db.scalar(select(func.count()).select_from(UserAchievement).where(UserAchievement.user_id == user_id))
    level = max(i for i, (start, _, _) in enumerate(STAGES) if count >= start)
    start, stage, name = STAGES[level]
    next_at = STAGES[level + 1][0] if level + 1 < len(STAGES) else None
    required = next_at - start if next_at is not None else None
    return TreeResponse(stage=stage, stage_name=name, level=level, sorting_count=count,
                        distinct_materials=distinct, unlocked_achievements=unlocked, next_stage_at=next_at,
                        progress_current=count - start, progress_required=required,
                        progress_percent=min(100, (count - start) * 100 // required) if required else 100)


def achievement_response(achievement: Achievement, earned: UserAchievement):
    return UserAchievementResponse(code=achievement.code, name=achievement.name, description=achievement.description,
                                   metric=achievement.metric, target=achievement.target, earned_at=earned.earned_at)


def earned_achievements(db, user_id: int, event_id: str | None = None):
    query = select(Achievement, UserAchievement).join(UserAchievement).where(UserAchievement.user_id == user_id)
    if event_id is not None:
        query = query.where(UserAchievement.event_id == event_id)
    return [achievement_response(a, earned) for a, earned in db.execute(
        query.order_by(UserAchievement.earned_at, Achievement.code))]


def award_achievements(db, event: SortingEvent):
    count, distinct = metrics(db, event.user_id)
    existing = set(db.scalars(select(UserAchievement.achievement_code).where(UserAchievement.user_id == event.user_id)))
    values = {"sorting_count": count, "distinct_materials": distinct}
    for definition in db.scalars(select(Achievement).order_by(Achievement.code)):
        if definition.code not in existing and values[definition.metric] >= definition.target:
            db.add(UserAchievement(user_id=event.user_id, achievement_code=definition.code,
                                   event_id=event.id, earned_at=event.created_at))
    db.flush()
