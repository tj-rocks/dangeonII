import pytest

from system.dungeon import Dungeon, Player


@pytest.fixture
def dungeon():
    world = Dungeon(4, 3)
    world.place(Player(), 0, 0)
    return world
