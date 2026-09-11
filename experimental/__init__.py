from flask import Blueprint

bp = Blueprint("experimental", __name__, url_prefix="/experimental")

from experimental import routes  # noqa: E402 — must follow Blueprint creation
