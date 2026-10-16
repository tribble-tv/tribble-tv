"""Admin routes for client accounts backed by Xtream credentials."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from backend.extensions import db
from backend.models import XtreamUser

admin_xtream_bp = Blueprint("admin_xtream", __name__, url_prefix="/admin/xtream")


def _int(name, default=0):
    raw = request.form.get(name)
    return int(raw) if raw not in (None, "") else default


@admin_xtream_bp.route("/")
def xtream_users_index():
    accounts = XtreamUser.query.order_by(XtreamUser.username).all()
    return render_template("admin/xtream_users/index.html", users=accounts)


@admin_xtream_bp.route("/new", methods=["GET", "POST"])
def xtream_users_new():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Usuario e senha sao obrigatorios.", "error")
            return render_template("admin/xtream_users/form.html", user=None)

        exists = XtreamUser.query.filter_by(username=username).first()
        if exists:
            flash(f"Conta '{username}' ja existe.", "error")
            return render_template("admin/xtream_users/form.html", user=None)

        user = XtreamUser(
            username=username,
            is_active=request.form.get("is_active") == "on",
            max_connections=_int("max_connections", 1),
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash(f"Conta '{username}' criada com sucesso.", "success")
        return redirect(url_for("admin_xtream.xtream_users_index"))

    return render_template("admin/xtream_users/form.html", user=None)


@admin_xtream_bp.route("/<int:id>/edit", methods=["GET", "POST"])
def xtream_users_edit(id):
    user = XtreamUser.query.get_or_404(id)

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username:
            flash("Usuario e obrigatorio.", "error")
            return render_template("admin/xtream_users/form.html", user=user)

        if username != user.username:
            exists = XtreamUser.query.filter_by(username=username).first()
            if exists:
                flash(f"Conta '{username}' ja existe.", "error")
                return render_template("admin/xtream_users/form.html", user=user)

        user.username = username
        user.is_active = request.form.get("is_active") == "on"
        user.max_connections = _int("max_connections", 1)

        if password:
            user.set_password(password)

        db.session.commit()
        flash(f"Conta '{username}' atualizada com sucesso.", "success")
        return redirect(url_for("admin_xtream.xtream_users_index"))

    return render_template("admin/xtream_users/form.html", user=user)


@admin_xtream_bp.route("/<int:id>/toggle", methods=["POST"])
def xtream_users_toggle(id):
    user = XtreamUser.query.get_or_404(id)
    user.is_active = not user.is_active
    db.session.commit()

    status = "ativada" if user.is_active else "desativada"
    flash(f"Conta '{user.username}' {status}.", "success")
    return redirect(url_for("admin_xtream.xtream_users_index"))


@admin_xtream_bp.route("/<int:id>/delete", methods=["POST"])
def xtream_users_delete(id):
    user = XtreamUser.query.get_or_404(id)
    username = user.username
    db.session.delete(user)
    db.session.commit()

    flash(f"Conta '{username}' removida.", "success")
    return redirect(url_for("admin_xtream.xtream_users_index"))
