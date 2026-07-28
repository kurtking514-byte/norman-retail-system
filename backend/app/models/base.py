from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import all model modules so Alembic's autogenerate can see every table.
import app.models.product  # noqa: E402, F401
import app.models.customer  # noqa: E402, F401
import app.models.reservation  # noqa: E402, F401
import app.models.repair  # noqa: E402, F401
import app.models.business  # noqa: E402, F401
import app.models.notification  # noqa: E402, F401
