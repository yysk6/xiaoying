import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(request, monkeypatch):
    if request.node.get_closest_marker("live"):
        if not request.config.getoption("--live"):
            pytest.skip("Use --live explicitly to enable paid model evaluation")
        return

    def forbidden(*args, **kwargs):
        raise AssertionError("Network access is forbidden in offline tests")

    monkeypatch.setattr(socket.socket, "connect", forbidden)


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="Explicitly enable real model calls")
