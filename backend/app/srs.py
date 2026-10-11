from datetime import datetime, timezone
from fsrs import Card as FSRSCard, Rating, Scheduler
from .models import Card

scheduler = Scheduler()

def review(card: Card, rating: int, now: datetime | None = None):
    instant = now or datetime.now(timezone.utc)
    state = FSRSCard.from_json(card.fsrs_state) if card.fsrs_state else FSRSCard()
    state, log = scheduler.review_card(state, Rating(rating), review_datetime=instant)
    card.fsrs_state = state.to_json()
    card.due_at = state.due.astimezone(timezone.utc).replace(tzinfo=None)
    card.version += 1
    return log.to_json()
