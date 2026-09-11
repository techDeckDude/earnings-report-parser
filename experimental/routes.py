from flask import render_template
from experimental import bp


@bp.route("/themes")
def themes():
    return render_template("experimental/themes.html")
