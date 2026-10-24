"""A running server has to say what it is.

A server left running across commits keeps serving the routes it started with
while the working tree moves on, and the symptom is a 404 for a route that is
plainly there in the code. That is not a theory: /spare-parts-return answered
404 for a whole session while a freshly built app answered 200, because the
worker had started before the commit that registered it.

So startup states the commit, the route count and the database. One line turns
"the code is missing the route" into "this process predates the route".
"""

import logging
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import session as session_module
from app.database.base import Base

STARTUP_FACTS = re.compile(
    r"Startup facts: commit=(?P<commit>\S+) routes=(?P<routes>\d+) database=(?P<database>.+)$"
)


@pytest.fixture(scope="module")
def app():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(session_module, "SessionLocal", TestingSession)

        from web import main

        patch.setattr(main, "init_db", lambda: None)
        patch.setattr(main, "create_default_admin", lambda: None)

        application = main.create_app()
        application.dependency_overrides[session_module.get_db] = override_get_db
        yield application


def test_route_count_sees_inside_the_included_routers(app):
    """A flat count hides almost everything on this FastAPI."""
    from web.main import _route_count

    total = _route_count(app)
    flat = len(app.routes)

    assert total > flat, (
        f"_route_count saw {total}, no more than a flat scan of app.routes "
        f"({flat}) -- it is not walking the included routers"
    )
    assert total > 100, f"only {total} routes counted; that cannot be the whole app"


def test_route_count_finds_a_route_registered_through_a_router(app):
    """The count has to include routers, not just directly added routes."""
    from web.main import _route_count

    # /spare-parts-return arrives through include_router, not add_api_route
    before = _route_count(app)
    app.add_api_route("/a-route-that-did-not-exist", lambda: None, methods=["GET"])

    try:
        assert _route_count(app) == before + 1
    finally:
        app.router.routes.pop()


def test_the_commit_is_reported_even_when_git_cannot_answer():
    from web import main

    commit = main._git_commit()

    assert commit and commit != " ", "no commit reported at all"
    assert re.fullmatch(r"[0-9a-f]{7,40}|unknown", commit), (
        f"unexpected commit marker: {commit!r}"
    )


def test_startup_states_the_commit_the_routes_and_the_database(app, caplog):
    with caplog.at_level(logging.INFO):
        with TestClient(app):
            pass

    facts = [m.getMessage() for m in caplog.records if "Startup facts:" in m.getMessage()]
    assert facts, "startup never said which commit / routes / database it is running"

    match = STARTUP_FACTS.search(facts[-1])
    assert match, f"the startup line does not carry the facts: {facts[-1]!r}"

    assert match.group("commit"), "no commit on the startup line"
    assert int(match.group("routes")) > 100, match.group("routes")
    assert match.group("database").strip(), "no database on the startup line"