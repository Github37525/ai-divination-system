import unittest

from scripts.validate_native_clients import validate


class NativeClientContractTests(unittest.TestCase):
    def test_native_clients_follow_shared_contract(self) -> None:
        validate()


if __name__ == "__main__":
    unittest.main()
