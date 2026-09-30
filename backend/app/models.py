"""Compatibility import point for SQLAlchemy metadata.

Models live in domain modules. Importing this module registers every table on Base.metadata.
"""

from app.accounts.models import *  # noqa: F401,F403
from app.ai.models import *  # noqa: F401,F403
from app.learning.models import *  # noqa: F401,F403
from app.memberships.models import *  # noqa: F401,F403
from app.organizations.models import *  # noqa: F401,F403
from app.study_profiles.models import *  # noqa: F401,F403
from app.subscriptions.models import *  # noqa: F401,F403
