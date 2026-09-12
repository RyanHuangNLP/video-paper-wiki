import unittest

from add import add


class AddTests(unittest.TestCase):
    def test_add_positive(self):
        self.assertEqual(add(2, 3), 5)

    def test_add_zero(self):
        self.assertEqual(add(0, 4), 4)


if __name__ == "__main__":
    unittest.main()
