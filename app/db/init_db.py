from app.db.session import Base, engine
from app.models import commit, evaluation, group, group_user, ranking, repository, user


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
