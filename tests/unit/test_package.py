import importlib
from importlib.metadata import version


def test_minimal_package_is_installed():
    package = importlib.import_module("content_planner")
    assert package.__version__ == version("xiaoying-content-planner") == "0.1.0"
