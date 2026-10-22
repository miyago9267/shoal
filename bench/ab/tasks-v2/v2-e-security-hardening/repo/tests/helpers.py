from deskapi.app import build_app


def make_app():
    app = build_app()
    admin = app.store.add_user("ada", role="admin")
    agent = app.store.add_user("bob", role="agent")
    other = app.store.add_user("cy", role="agent")
    app.tokens.issue("adm", "admin-secret-1", admin["id"])
    app.tokens.issue("bob", "bob-secret-22", agent["id"])
    app.tokens.issue("cy", "cy-secret-333", other["id"])
    return app, admin, agent, other


def auth(token):
    return {"Authorization": f"Bearer {token}"}


ADMIN = auth("adm.admin-secret-1")
BOB = auth("bob.bob-secret-22")
CY = auth("cy.cy-secret-333")
