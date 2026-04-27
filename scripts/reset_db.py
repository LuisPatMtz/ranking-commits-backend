from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.session import Base, engine
from app.models import commit, docente_invite, evaluation, group, group_share_token, group_student_invite, group_user, participant, project_evaluation, ranking, repository, user


if __name__ == "__main__":
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("Database reset completed successfully")
